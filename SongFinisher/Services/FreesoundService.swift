import Foundation

/// One search result from Freesound: enough to show in a list and, if chosen,
/// download as a usable local audio file.
struct FreesoundSound: Decodable, Identifiable {
    let id: Int
    let name: String
    let username: String
    let duration: Double
    /// Keyed by preview type ("preview-hq-mp3", "preview-lq-ogg", ...). Kept as
    /// a raw dictionary rather than fixed fields since Freesound's exact key set
    /// isn't a stable contract worth hardcoding — `previewURL` just picks the
    /// best one available.
    let previews: [String: String]
    let license: String

    var previewURL: URL? {
        let preferredKeys = ["preview-hq-mp3", "preview-lq-mp3", "preview-hq-ogg", "preview-lq-ogg"]
        for key in preferredKeys {
            if let value = previews[key], let url = URL(string: value) { return url }
        }
        return previews.values.first.flatMap(URL.init(string:))
    }

    /// Short, human-readable license label — surfaced in the UI since it
    /// matters whether a sample can be used in something the user publishes.
    var licenseLabel: String {
        if license.contains("publicdomain/zero") { return "CC0 · Public Domain" }
        if license.contains("licenses/by-nc") { return "CC BY-NC" }
        if license.contains("licenses/by-sa") { return "CC BY-SA" }
        if license.contains("licenses/by") { return "CC BY" }
        if license.contains("licenses/sampling+") { return "Sampling+" }
        return "See license"
    }
}

enum FreesoundError: LocalizedError {
    case missingAPIKey
    case requestFailed(String)
    case noPreviewAvailable

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "Add a Freesound API key in Settings to browse sounds."
        case .requestFailed(let message):
            return message
        case .noPreviewAvailable:
            return "This sound has no preview audio available."
        }
    }
}

/// Search and preview-download against the Freesound API
/// (https://freesound.org/docs/api/). Uses simple token auth — Song Finisher
/// only needs search and preview audio, not the OAuth2-gated original-quality
/// downloads or account actions, so there's no login flow, just an API key.
enum FreesoundService {
    private static let searchEndpoint = URL(string: "https://freesound.org/apiv2/search/text/")!

    /// DevSecrets.plist wins over the Keychain, so dropping a key in the file
    /// works without touching the in-app settings screen.
    static var apiKey: String? {
        DevSecrets.freesoundAPIKey ?? KeychainService.loadAPIKey(for: .freesoundAPIKey)
    }

    static var isConfigured: Bool {
        apiKey?.isEmpty == false
    }

    static func search(query: String) async throws -> [FreesoundSound] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }
        guard let apiKey, !apiKey.isEmpty else {
            throw FreesoundError.missingAPIKey
        }

        var components = URLComponents(url: searchEndpoint, resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "query", value: trimmed),
            URLQueryItem(name: "fields", value: "id,name,username,duration,previews,license"),
            URLQueryItem(name: "page_size", value: "30")
        ]

        var request = URLRequest(url: components.url!)
        request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw FreesoundError.requestFailed("Couldn't reach Freesound: \(error.localizedDescription)")
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw FreesoundError.requestFailed("No response from Freesound.")
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw FreesoundError.requestFailed("Freesound error (\(httpResponse.statusCode)). Check that your API key is correct.")
        }

        struct SearchResponse: Decodable { let results: [FreesoundSound] }
        do {
            return try JSONDecoder().decode(SearchResponse.self, from: data).results
        } catch {
            throw FreesoundError.requestFailed("Couldn't read Freesound's response.")
        }
    }

    /// Downloads a sound's preview audio to a local temp file so it can be
    /// previewed and saved through the same flow as a recorded or imported take.
    static func downloadPreview(_ sound: FreesoundSound) async throws -> URL {
        guard let previewURL = sound.previewURL else {
            throw FreesoundError.noPreviewAvailable
        }

        let tempURL: URL
        let response: URLResponse
        do {
            (tempURL, response) = try await URLSession.shared.download(from: previewURL)
        } catch {
            throw FreesoundError.requestFailed("Couldn't download that sound: \(error.localizedDescription)")
        }
        guard let httpResponse = response as? HTTPURLResponse, (200..<300).contains(httpResponse.statusCode) else {
            throw FreesoundError.requestFailed("Couldn't download that sound's preview.")
        }

        let ext = previewURL.pathExtension.isEmpty ? "mp3" : previewURL.pathExtension
        let destURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("freesound-\(sound.id)-\(UUID().uuidString)")
            .appendingPathExtension(ext)
        if FileManager.default.fileExists(atPath: destURL.path) {
            try FileManager.default.removeItem(at: destURL)
        }
        try FileManager.default.moveItem(at: tempURL, to: destURL)
        return destURL
    }
}
