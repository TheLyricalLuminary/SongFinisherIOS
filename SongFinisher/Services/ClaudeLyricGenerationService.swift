import Foundation

/// Optional AI-backed lyric generator using Anthropic's Claude API. Requires an
/// API key (configured in Lyric Settings, stored in the Keychain — never in
/// UserDefaults or the SwiftData store). When no key is configured,
/// `LyricGenerationServiceFactory` falls back to `LocalLyricGenerationService`
/// instead of constructing this type.
///
/// Every craft setting is passed through in the brief, and the style-word ban is
/// both stated up front and verified on the response — a violation triggers one
/// corrective retry.
struct ClaudeLyricGenerationService: LyricGenerationService {
    var apiKey: String
    var model: String = "claude-sonnet-5"

    private static let endpoint = URL(string: "https://api.anthropic.com/v1/messages")!

    private static let systemPrompt = """
    You are a songwriter helping a musician finish a song they have already recorded. \
    Write original, specific, non-cliché lyrics that fit the brief you are given.

    Craft rules:
    - Favor concrete, sensory, surprising imagery. Avoid stock phrases ("burning like \
    fire", "shining stars", "broken heart") and avoid abstract emotion words where a \
    physical detail would land harder.
    - Honor the requested rhyme scheme, rhyme type, and syllable target. The syllable \
    target is per line; stay within about one syllable of it so the lines sit evenly on \
    the singer's existing rhythm.
    - Let the meter and tempo shape phrasing: put natural stresses where the strong \
    beats fall, and keep line lengths singable at the given tempo.
    - Structure the song as [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus] \
    — each label on its own line, followed by that section's lines. Four lines per verse \
    and chorus, two to four for the bridge.
    - The chorus must be worded identically every time it repeats.

    Return ONLY the lyrics with their section labels. No commentary, no preamble, no \
    quotation marks around the lyrics.
    """

    func generateLyrics(_ request: LyricGenerationRequest) async throws -> GeneratedLyrics {
        let prompt = request.trimmedPrompt
        guard !prompt.isEmpty else { throw LyricGenerationError.emptyPrompt }
        let trimmedKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedKey.isEmpty else { throw LyricGenerationError.missingAPIKey }

        let banned = request.bannedWords
        let brief = Self.brief(for: request)

        var text = try await send(userMessage: brief, apiKey: trimmedKey)

        // The style-word ban is a hard rule, so verify rather than trust. One
        // corrective retry, then take what we get rather than failing the user.
        if StyleWordGuard.containsBannedWord(text, banned: banned) {
            let correction = """
            \(brief)

            Your previous draft used forbidden style-direction words. Rewrite the lyrics \
            completely. These words, and their variants, must not appear anywhere in the \
            lyrics: \(banned.joined(separator: ", ")). Keep the style's feeling — just \
            never name it.
            """
            text = try await send(userMessage: correction, apiKey: trimmedKey)
        }

        guard !text.isEmpty else { throw LyricGenerationError.emptyResponse }
        return GeneratedLyrics(text: text)
    }

    /// Turns the request into an explicit brief. Only settings the user actually
    /// specified are mentioned, so blank fields don't invent constraints.
    private static func brief(for request: LyricGenerationRequest) -> String {
        let settings = request.settings
        var lines: [String] = ["THEME: \(request.trimmedPrompt)"]

        let style = settings.trimmedStyle
        if !style.isEmpty {
            lines.append("""
            STYLE DIRECTION: \(style)
            Let this drive the tone, vocabulary, attitude, imagery and rhythmic feel of the writing.
            HARD RULE: the style words themselves must never appear in the lyrics. Do not use \
            these words or their variants anywhere: \(request.bannedWords.joined(separator: ", ")). \
            Evoke the style; never name it.
            """)
        }

        lines.append("RHYME SCHEME: \(settings.rhymeScheme.rawValue)\(Self.schemeExplanation(settings.rhymeScheme))")
        lines.append("RHYME TYPE: \(Self.rhymeTypeExplanation(settings.effectiveRhymeTypes))")
        lines.append("SYLLABLES PER LINE: aim for \(settings.syllableTarget) (±1)")

        var musical = ["\(settings.timeSignature.rawValue) — \(settings.timeSignature.feelDescription)"]
        if settings.bpm > 0 { musical.append("\(settings.bpm) BPM") }
        let key = settings.trimmedKey
        if !key.isEmpty { musical.append("key of \(key)") }
        lines.append("MUSICAL CONTEXT: " + musical.joined(separator: " · ")
            + "\nPhrase the lines so stressed syllables land on strong beats in this meter and tempo.")

        return lines.joined(separator: "\n\n")
    }

    private static func schemeExplanation(_ scheme: RhymeScheme) -> String {
        switch scheme {
        case .aabb: return " — in each four-line section, lines 1&2 rhyme and lines 3&4 rhyme"
        case .abab: return " — in each four-line section, lines 1&3 rhyme and lines 2&4 rhyme"
        case .abba: return " — in each four-line section, lines 1&4 rhyme and lines 2&3 rhyme"
        case .abcb: return " — in each four-line section, only lines 2&4 rhyme; lines 1 and 3 do not"
        case .aaaa: return " — in each four-line section, all four lines rhyme with each other"
        case .free: return " — no rhyme requirement; prioritize natural phrasing over rhyme"
        }
    }

    private static func rhymeTypeExplanation(_ types: [RhymeType]) -> String {
        let descriptions = types.map { type -> String in
            switch type {
            case .end: return "true end rhymes on the final word of each line"
            case .slant: return "near/slant rhymes (shared vowel or shared closing consonants, not exact)"
            case .internalRhyme: return "internal rhymes inside individual lines as well"
            }
        }
        return descriptions.joined(separator: "; also use ")
    }

    // MARK: - Networking

    private func send(userMessage: String, apiKey: String) async throws -> String {
        var urlRequest = URLRequest(url: Self.endpoint)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        urlRequest.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload: [String: Any] = [
            "model": model,
            "max_tokens": 1024,
            "system": Self.systemPrompt,
            "messages": [["role": "user", "content": userMessage]]
        ]
        urlRequest.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: urlRequest)
        } catch {
            throw LyricGenerationError.requestFailed("Couldn't reach the lyric service: \(error.localizedDescription)")
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw LyricGenerationError.requestFailed("No response from the lyric service.")
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = Self.errorMessage(from: data) ?? "Lyric service error (\(httpResponse.statusCode))."
            throw LyricGenerationError.requestFailed(message)
        }

        let decoded: MessagesResponse
        do {
            decoded = try JSONDecoder().decode(MessagesResponse.self, from: data)
        } catch {
            throw LyricGenerationError.requestFailed("Couldn't read the lyric service's response.")
        }

        return decoded.content
            .compactMap(\.text)
            .joined()
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func errorMessage(from data: Data) -> String? {
        struct ErrorBody: Decodable {
            struct Detail: Decodable { let message: String }
            let error: Detail
        }
        return try? JSONDecoder().decode(ErrorBody.self, from: data).error.message
    }

    private struct MessagesResponse: Decodable {
        struct ContentBlock: Decodable {
            let type: String
            let text: String?
        }
        let content: [ContentBlock]
    }
}
