import Foundation

/// Reads API keys from a gitignored `DevSecrets.plist` bundled into the app at
/// build time, so keys can be set by editing a file instead of typing them into
/// the in-app settings screens.
///
/// Precedence is: this file first, Keychain second (see the `resolvedKey`
/// callers). The file is gitignored — `DevSecrets.example.plist` is the
/// committed template showing its shape.
enum DevSecrets {
    private static let values: [String: String] = {
        guard let url = Bundle.main.url(forResource: "DevSecrets", withExtension: "plist"),
              let data = try? Data(contentsOf: url),
              let plist = try? PropertyListSerialization.propertyList(from: data, format: nil),
              let dict = plist as? [String: String] else {
            return [:]
        }
        return dict.compactMapValues { value in
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
    }()

    static var freesoundAPIKey: String? { values["FreesoundAPIKey"] }
    static var claudeAPIKey: String? { values["ClaudeAPIKey"] }
}
