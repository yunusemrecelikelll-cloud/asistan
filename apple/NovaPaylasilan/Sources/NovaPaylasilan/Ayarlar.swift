import Foundation
// Keychain çağrıları (SecItemAdd, kSecClass…) Security çerçevesinde;
// Foundation onları getirmiyor.
import Security

/// Sunucu adresi ve belirteç.
///
/// Belirteç Keychain'de tutuluyor; UserDefaults'ta değil. Yedeklemeye ve
/// cihaz dökümüne düz metin parola bırakmamak için.
public final class Ayarlar {

    public static let ortak = Ayarlar()

    private let d = UserDefaults.standard
    private let sunucuAnahtar = "nova.sunucu"
    private let keychainHesap = "nova.belirtec"

    private init() {}

    /// Örn. "100.x.y.z:8770" (Tailscale) ya da "192.168.1.20:8770" (yerel ağ).
    public var sunucu: String {
        get { d.string(forKey: sunucuAnahtar) ?? "" }
        set { d.set(newValue, forKey: sunucuAnahtar) }
    }

    /// Yerel ağdaki adres. Varsa saat ve telefon önce bunu deniyor: aynı
    /// ağdayken Tailscale üzerinden gitmek tur başına 20-60 ms ekliyor.
    public var yerelSunucu: String {
        get { d.string(forKey: "nova.yerel") ?? "" }
        set { d.set(newValue, forKey: "nova.yerel") }
    }

    public var wsAdresi: URL? { adres(sunucu, yol: "/ws") }
    public var yerelWsAdresi: URL? { adres(yerelSunucu, yol: "/ws") }

    private func adres(_ konak: String, yol: String) -> URL? {
        guard !konak.isEmpty else { return nil }
        let temiz = konak
            .replacingOccurrences(of: "http://", with: "")
            .replacingOccurrences(of: "https://", with: "")
            .trimmingCharacters(in: .whitespaces)
        return URL(string: "ws://\(temiz)\(yol)")
    }

    // MARK: - Keychain

    public var belirtec: String {
        get {
            var sorgu: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrAccount as String: keychainHesap,
                kSecReturnData as String: true,
                kSecMatchLimit as String: kSecMatchLimitOne
            ]
            var sonuc: AnyObject?
            let durum = withUnsafeMutablePointer(to: &sonuc) {
                SecItemCopyMatching(sorgu as CFDictionary, $0)
            }
            sorgu.removeAll()
            guard durum == errSecSuccess, let veri = sonuc as? Data else {
                return ""
            }
            return String(data: veri, encoding: .utf8) ?? ""
        }
        set {
            let temel: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrAccount as String: keychainHesap
            ]
            SecItemDelete(temel as CFDictionary)
            guard !newValue.isEmpty else { return }
            var ekle = temel
            ekle[kSecValueData as String] = Data(newValue.utf8)
            // Cihaz kilitliyken de bağlanabilelim (saat arka planda konuşuyor),
            // ama yedeğe çıkmasın.
            ekle[kSecAttrAccessible as String] =
                kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(ekle as CFDictionary, nil)
        }
    }

    public var kurulumTamam: Bool {
        !sunucu.isEmpty || !yerelSunucu.isEmpty
    }
}
