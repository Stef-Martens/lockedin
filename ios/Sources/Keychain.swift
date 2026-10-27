import Foundation
import Security

/// Strings kept in the iPhone's Keychain, under this app's own service name.
enum Keychain {
    private static let service = "be.stefmartens.lockedin.watch"

    static func read(_ account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Replaces whatever was stored; false when the Keychain refused.
    static func save(_ value: String, account: String) -> Bool {
        let item: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(item as CFDictionary)
        var add = item
        add[kSecValueData as String] = Data(value.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
    }
}

/// Where the feed lives and the watch key that unlocks it.
struct Connection: Equatable {
    let base: URL
    let key: String

    /// Accepts "lockedin.vercel.app" as well as a full https:// address.
    init?(address: String, key: String) {
        var text = address.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.contains("://") { text = "https://" + text }
        let key = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: text), ["https", "http"].contains(url.scheme?.lowercased()),
              url.host() != nil, !key.isEmpty else { return nil }
        self.base = url
        self.key = key
    }

    static func saved() -> Connection? {
        guard let address = Keychain.read("address"), let key = Keychain.read("key") else { return nil }
        return Connection(address: address, key: key)
    }

    func save() -> Bool {
        Keychain.save(base.absoluteString, account: "address") && Keychain.save(key, account: "key")
    }
}
