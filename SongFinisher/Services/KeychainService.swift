import Foundation
import Security

/// Minimal Keychain wrapper for the app's optional API keys (Claude,
/// Freesound). Kept out of UserDefaults/SwiftData since they're secrets, not
/// app data.
enum KeychainService {
    enum Key: String {
        case claudeAPIKey
        case freesoundAPIKey
    }

    private static let service = "com.markwamigoni.songfinisher"

    static func saveAPIKey(_ key: String, for keyType: Key) {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: keyType.rawValue
        ]
        SecItemDelete(baseQuery as CFDictionary)

        guard !trimmed.isEmpty else { return }

        var addQuery = baseQuery
        addQuery[kSecValueData as String] = Data(trimmed.utf8)
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(addQuery as CFDictionary, nil)
    }

    static func loadAPIKey(for keyType: Key) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: keyType.rawValue,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess,
              let data = result as? Data,
              let key = String(data: data, encoding: .utf8),
              !key.isEmpty else {
            return nil
        }
        return key
    }
}
