import Foundation

/// `backend/kanal.py` içindeki WebSocket protokolünün Swift karşılığı.
///
/// Protokol bilerek sade: metin çerçeveleri JSON, ses çerçeveleri ham ikili.
/// Bir ikili çerçeve HER ZAMAN kendisini tarif eden JSON çerçevesinin hemen
/// ardından gelir; böylece istemcinin ayrıca eşleme yapması gerekmiyor ve
/// çerçeve başına ek bir başlık taşınmıyor.
public enum Protokol {

    // MARK: - Sunucudan gelen

    public enum Gelen {
        /// Bağlantı kuruldu, hangi ses kullanılıyor.
        case hazir(ses: String)
        /// Parola/belirteç geçersiz.
        case yetkisiz
        /// Konuşma tanıma sonucu — kullanıcının söylediği.
        case yazi(metin: String, sureMs: Int?)
        /// Asistanın yanıtı. `kismi` ise daha fazlası geliyor.
        case yanit(metin: String, niyet: String?, kismi: Bool, sureMs: Int?)
        /// Bir ses parçası duyuruluyor; ikili çerçeve BUNDAN sonra gelir.
        case parca(sira: Int, bayt: Int, bicim: String, metin: String)
        /// Turun sonu.
        case bitti
        /// Sunucudan kendiliğinden gelen değişiklik bildirimi.
        case olay(tur: String, veri: [String: Any])
        case nabiz
        case hata(mesaj: String)

        public static func coz(_ veri: Data) -> Gelen? {
            guard
                let ham = try? JSONSerialization.jsonObject(with: veri),
                let d = ham as? [String: Any],
                let tur = d["tur"] as? String
            else { return nil }

            switch tur {
            case "hazir":
                return .hazir(ses: d["ses"] as? String ?? "ses1")
            case "yetkisiz":
                return .yetkisiz
            case "yazi":
                return .yazi(metin: d["metin"] as? String ?? "",
                             sureMs: d["sure_ms"] as? Int)
            case "yanit":
                return .yanit(metin: d["metin"] as? String ?? "",
                              niyet: d["niyet"] as? String,
                              kismi: d["kismi"] as? Bool ?? false,
                              sureMs: d["sure_ms"] as? Int)
            case "parca":
                return .parca(sira: d["sira"] as? Int ?? 0,
                              bayt: d["bayt"] as? Int ?? 0,
                              bicim: d["bicim"] as? String ?? "audio/wav",
                              metin: d["metin"] as? String ?? "")
            case "bitti":
                return .bitti
            case "nabiz":
                return .nabiz
            case "hata":
                return .hata(mesaj: d["mesaj"] as? String ?? "bilinmeyen hata")
            case "olay":
                // Olay İÇ İÇE geliyor. Düz yayılsaydı olayın kendi "tur"
                // alanı (gorev, mesaj…) dıştaki "olay" değerini ezerdi ve
                // "bitti" adlı bir olay turu erkenden kapatırdı.
                let ic = d["olay"] as? [String: Any] ?? [:]
                return .olay(tur: ic["tur"] as? String ?? "bilinmeyen",
                             veri: ic)
            default:
                // Bilinmeyen çerçeveyi yok sayıyoruz: sunucu protokole yeni
                // bir tür eklediğinde eski istemci çökmesin.
                return nil
            }
        }
    }

    // MARK: - Sunucuya giden

    public enum Giden {
        case giris(belirtec: String)
        case metin(String, sesli: Bool)
        case sesBasla
        case sesBitti(uzanti: String, sesli: Bool)
        case nabiz

        public func kodla() -> Data {
            let d: [String: Any]
            switch self {
            case .giris(let b):
                d = ["tur": "giris", "belirtec": b]
            case .metin(let m, let sesli):
                d = ["tur": "metin", "metin": m, "sesli": sesli]
            case .sesBasla:
                d = ["tur": "ses_basla"]
            case .sesBitti(let uzanti, let sesli):
                d = ["tur": "ses_bitti", "uzanti": uzanti, "sesli": sesli]
            case .nabiz:
                d = ["tur": "nabiz"]
            }
            return (try? JSONSerialization.data(withJSONObject: d)) ?? Data()
        }
    }
}
