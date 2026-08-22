import Foundation

/// A suggested THEME and STYLE for a project, generated from whatever signal
/// is genuinely available. When a transcript exists, THEME is grounded in
/// what was actually sung. When there's no transcript (a wordless
/// instrumental someone plans to practice singing over), THEME instead
/// becomes a tempo-informed creative starting idea — explicitly a suggestion
/// for inspiration, never framed as something detected in audio that has no
/// words in it yet.
struct VibeSuggestion: Equatable {
    var theme: String?
    var style: String
}

enum VibeSuggestionError: LocalizedError {
    case missingAPIKey
    case requestFailed(String)
    case emptyResponse

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "Add a Claude API key in Settings to auto-suggest theme and style."
        case .requestFailed(let message):
            return message
        case .emptyResponse:
            return "Couldn't get a suggestion this time. Try again."
        }
    }
}

/// Suggests THEME and STYLE by asking Claude (text only — reuses the same API
/// key as lyric generation, no new account or audio-capable model needed).
enum ClaudeVibeSuggestionService {
    private static let endpoint = URL(string: "https://api.anthropic.com/v1/messages")!
    private static let model = "claude-sonnet-5"

    private static let systemPrompt = """
    You help a songwriter name the THEME (subject/mood, a short concrete phrase) and \
    STYLE (genre/tone descriptors) of a song they're working on, based only on what's \
    actually known about it. Be specific, not generic.

    If a transcript of sung or spoken words is provided, ground the theme in what those \
    words are actually about — never invent an unrelated subject.

    If no transcript is given, this is a wordless instrumental take the songwriter plans \
    to practice singing over — there are no words yet to ground a theme in. In that case, \
    suggest a THEME as a creative starting idea for what they could sing about, informed \
    by the mood tempo and time signature suggest. This must read as a suggestion for \
    inspiration, in the same short-phrase format as a real theme (e.g. "leaving a small \
    town at night") — never phrase it as something you detected or heard in the audio, \
    since there are no words there to detect.

    Respond with ONLY a JSON object of the exact shape {"theme": "...", "style": "..."} — \
    no commentary, no markdown code fences, nothing else.
    """

    static func suggestVibe(
        transcript: String?,
        bpm: Int?,
        timeSignature: TimeSignature
    ) async throws -> VibeSuggestion {
        guard let apiKey = LyricGenerationServiceFactory.apiKey, !apiKey.isEmpty else {
            throw VibeSuggestionError.missingAPIKey
        }

        var lines: [String] = []
        let trimmedTranscript = transcript?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmedTranscript.isEmpty {
            lines.append("TRANSCRIPT OF WHAT WAS SUNG: \"\(trimmedTranscript)\"")
        } else {
            lines.append("No words were recognized in this take — it's a wordless instrumental the songwriter is about to practice singing over. Suggest a creative theme starting idea, not a detected one.")
        }
        lines.append("TIME SIGNATURE: \(timeSignature.rawValue) — \(timeSignature.feelDescription)")
        if let bpm, bpm > 0 { lines.append("TEMPO: \(bpm) BPM") }

        let text = try await send(userMessage: lines.joined(separator: "\n"), apiKey: apiKey)

        guard let jsonText = extractJSONObject(from: text), let jsonData = jsonText.data(using: .utf8) else {
            throw VibeSuggestionError.requestFailed("Couldn't parse the suggestion.")
        }
        struct SuggestionPayload: Decodable { let theme: String; let style: String }
        guard let payload = try? JSONDecoder().decode(SuggestionPayload.self, from: jsonData) else {
            throw VibeSuggestionError.requestFailed("Couldn't parse the suggestion.")
        }

        let trimmedTheme = payload.theme.trimmingCharacters(in: .whitespacesAndNewlines)
        return VibeSuggestion(theme: trimmedTheme.isEmpty ? nil : trimmedTheme, style: payload.style)
    }

    /// Claude sometimes wraps JSON in commentary or code fences despite
    /// instructions not to — slicing between the first `{` and last `}`
    /// handles that uniformly instead of trying to strip specific formats.
    private static func extractJSONObject(from text: String) -> String? {
        guard let start = text.firstIndex(of: "{"), let end = text.lastIndex(of: "}"), start < end else {
            return nil
        }
        return String(text[start...end])
    }

    // MARK: - Networking

    private static func send(userMessage: String, apiKey: String) async throws -> String {
        var urlRequest = URLRequest(url: endpoint)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        urlRequest.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload: [String: Any] = [
            "model": model,
            "max_tokens": 256,
            "system": systemPrompt,
            "messages": [["role": "user", "content": userMessage]]
        ]
        urlRequest.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: urlRequest)
        } catch {
            throw VibeSuggestionError.requestFailed("Couldn't reach the lyric service: \(error.localizedDescription)")
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw VibeSuggestionError.requestFailed("No response from the lyric service.")
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw VibeSuggestionError.requestFailed("Lyric service error (\(httpResponse.statusCode)).")
        }

        struct MessagesResponse: Decodable {
            struct ContentBlock: Decodable { let text: String? }
            let content: [ContentBlock]
        }
        let decoded: MessagesResponse
        do {
            decoded = try JSONDecoder().decode(MessagesResponse.self, from: data)
        } catch {
            throw VibeSuggestionError.requestFailed("Couldn't read the lyric service's response.")
        }

        let text = decoded.content.compactMap(\.text).joined().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { throw VibeSuggestionError.emptyResponse }
        return text
    }
}
