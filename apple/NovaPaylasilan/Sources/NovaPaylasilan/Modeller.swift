import Foundation

/// Sunucudan gelen kayıtların Swift karşılığı.
///
/// Alanların çoğu isteğe bağlı (`?`) — bilerek. Sunucu yeni bir alan
/// eklediğinde ya da bir alanı boş bıraktığında uygulamanın çözümlemesi
/// tamamen düşmesin. Ekranda gösterdiğimizden fazlasını modellemiyoruz.

/// Hem `true/false` hem `1/0` kabul eden mantıksal değer.
///
/// SQLite'ta boolean tipi yok; sunucu bazı alanları int, bazılarını bool
/// döndürüyor — hatta AYNI alanı uca göre farklı: `/api/projeler`
/// `var_mi: true` derken `/api/projeler/{id}` `var_mi: 1` diyor.
///
/// `JSONDecoder` 1'i Bool'a çevirmiyor, `typeMismatch` fırlatıyor ve o tek
/// alan yüzünden BÜTÜN yanıtın çözümlenmesi düşüyor. Plan ekranının boş
/// görünmesinin sebebi tam olarak buydu: görevlerdeki `zorunlu: 1`.
public struct EsnekBool: Decodable, Equatable, Sendable {
    public let deger: Bool

    public init(_ d: Bool) { deger = d }

    public init(from cozucu: Decoder) throws {
        let k = try cozucu.singleValueContainer()
        if let b = try? k.decode(Bool.self) { deger = b }
        else if let i = try? k.decode(Int.self) { deger = i != 0 }
        else if let d = try? k.decode(Double.self) { deger = d != 0 }
        else if let s = try? k.decode(String.self) {
            deger = s == "1" || s.lowercased() == "true"
        } else { deger = false }
    }
}

extension Optional where Wrapped == EsnekBool {
    /// Alan yoksa varsayılanı kullan.
    public func deger(_ varsayilan: Bool) -> Bool { self?.deger ?? varsayilan }
}

// MARK: - Plan

public struct Gorev: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let baslik: String
    public let tarih: String
    public let saat: String
    public let sureDk: Int?
    public let durum: String
    public let oncelik: Int?
    public let zorunlu: EsnekBool?
    public let ayrinti: String?
    public let projeId: Int?
    public let projeAd: String?
    public let erteleme: Int?
    public let gercekDk: Int?

    enum CodingKeys: String, CodingKey {
        case id, baslik, tarih, saat, durum, oncelik, zorunlu, ayrinti,
             erteleme
        case sureDk = "sure_dk"
        case projeId = "proje_id"
        case projeAd = "proje_ad"
        case gercekDk = "gercek_dk"
    }

    public var zorunluMu: Bool { zorunlu.deger(true) }

    /// Görev saatinin tam tarihi. Bildirim kurmak için.
    public var zaman: Date? {
        let b = DateFormatter()
        b.locale = Locale(identifier: "en_US_POSIX")
        b.dateFormat = "yyyy-MM-dd HH:mm"
        b.timeZone = .current
        return b.date(from: "\(tarih) \(saat)")
    }

    public var bekliyor: Bool { durum == "bekliyor" || durum == "basladi" }
    public var tamam: Bool { durum == "tamam" }
    public var kacirildi: Bool { durum == "kacirildi" }
}

public struct Karne: Decodable, Equatable, Sendable {
    public let toplam: Int
    public let tamam: Int
    public let kacirildi: Int
    public let kalan: Int
    public let uyum: Double?
}

public struct Gun: Decodable, Equatable, Sendable {
    public let tarih: String
    public let gun: String
    public let saat: String?
    public let gorevler: [Gorev]
    public let siradaki: Gorev?
    public let karne: Karne?
}

public struct HaftaGunu: Decodable, Identifiable, Equatable, Sendable {
    public let tarih: String
    public let gun: String
    public let gorevler: [Gorev]?
    public let karne: Karne?
    public var id: String { tarih }
}

public struct Hafta: Decodable, Equatable, Sendable {
    public let baslangic: String
    public let bitis: String
    public let gunler: [HaftaGunu]
}

// MARK: - Projeler

public struct Proje: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let ad: String
    public let yol: String?
    public let varMi: EsnekBool?
    public let oturumSayisi: Int?
    public let notMetni: String?
    public let etiket: String?
    public let durum: String?
    public let tur: String?
    public let sonOturum: Double?

    enum CodingKeys: String, CodingKey {
        case id, ad, yol, durum, tur, etiket
        case varMi = "var_mi"
        case oturumSayisi = "oturum_sayisi"
        case notMetni = "not_metni"
        case sonOturum = "son_oturum"
    }

    public var diskteVar: Bool { varMi.deger(true) }
}

/// Proje ayrıntısı — /api/projeler/{id}
public struct ProjeDetay: Decodable, Equatable, Sendable {
    public let id: Int
    public let ad: String
    public let yol: String?
    public let varMi: EsnekBool?
    public let ozet: String?
    public let notMetni: String?
    public let oturumSayisi: Int?
    public let gitDurumu: GitDurumu?
    public let basliklar: [String]?
    public let brifing: String?

    enum CodingKeys: String, CodingKey {
        case id, ad, yol, ozet, basliklar, brifing
        case varMi = "var_mi"
        case notMetni = "not_metni"
        case oturumSayisi = "oturum_sayisi"
        case gitDurumu = "git_durumu"
    }

    public var diskteVar: Bool { varMi.deger(true) }
}

public struct GitDurumu: Decodable, Equatable, Sendable {
    public let dal: String?
    public let kirli: EsnekBool?
    public let degisen: Int?
    public let sonCommit: String?

    enum CodingKeys: String, CodingKey {
        case dal, kirli, degisen
        case sonCommit = "son_commit"
    }
}

// MARK: - Yaşam

public struct YasamKarti: Decodable, Identifiable, Equatable, Sendable {
    public let tur: String
    public let ad: String
    public let birim: String?
    public let bugun: Double?
    public let ortalama: Double?
    public let hedef: Double?
    public let durum: String?
    public var id: String { tur }
}

public struct YasamOzeti: Decodable, Equatable, Sendable {
    public let kartlar: [YasamKarti]
}

// MARK: - Atölye

/// Yazıcının üstünde şu an dönen baskı ve ne kadarının bittiği.
///
/// `ilerleme` sunucuda `baski.baski_durum` ile hesaplanıyor — makineye
/// sorarak değil, başlangıç saati ile tahmini süreden. Yüzde bu yüzden bir
/// TAHMİN; ekranda da öyle sunuluyor.
public struct BaskiIlerleme: Decodable, Equatable, Sendable {
    public let durum: String?
    public let gecenDk: Int?
    public let kalanDk: Int?
    public let yuzde: Int?
    public let bitti: EsnekBool?

    enum CodingKeys: String, CodingKey {
        case durum, yuzde
        case gecenDk = "gecen_dk"
        case kalanDk = "kalan_dk"
        case bitti
    }

    public var bittiMi: Bool { bitti.deger(false) }
}

public struct AktifBaski: Decodable, Equatable, Sendable {
    public let id: Int
    public let ad: String
    public let tahminiDk: Int?
    public let projeAd: String?
    public let ilerleme: BaskiIlerleme?

    enum CodingKeys: String, CodingKey {
        case id, ad, ilerleme
        case tahminiDk = "tahmini_dk"
        case projeAd = "proje_ad"
    }
}

public struct Yazici: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let ad: String
    public let model: String?
    public let durum: String?
    public let filament: String?
    public let filamentRenk: String?
    public let nozzle: String?
    public let toplamDk: Int?
    public let baskiSayisi: Int?
    public let notlar: String?
    public let aktifBaski: AktifBaski?

    enum CodingKeys: String, CodingKey {
        case id, ad, model, durum, filament, nozzle, notlar
        case filamentRenk = "filament_renk"
        case toplamDk = "toplam_dk"
        case baskiSayisi = "baski_sayisi"
        case aktifBaski = "aktif_baski"
    }

    /// Takılı filament tek satırda: "PLA · siyah · 0.4".
    public var filamentYazisi: String? {
        let p = [filament, filamentRenk, nozzle]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
        return p.isEmpty ? nil : p.joined(separator: " · ")
    }
}

public struct Atolye: Decodable, Equatable, Sendable {
    public let yazicilar: [Yazici]
}

public struct BaskiDosyasi: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let ad: String?
    public let yol: String?
    public let durum: String?
    public let boyut: Int?
    public let eklendi: Double?
    public let projeAd: String?

    enum CodingKeys: String, CodingKey {
        case id, ad, yol, durum, boyut, eklendi
        case projeAd = "proje_ad"
    }

    public var gorunenAd: String { ad ?? yol ?? "adsız" }

    /// "12.4 MB". Dilimleyicinin çıktısı megabayt ölçeğinde; kilobayt
    /// göstermek satırı gereksiz uzatıyor.
    public var boyutYazisi: String? {
        guard let b = boyut, b > 0 else { return nil }
        let mb = Double(b) / (1024 * 1024)
        return mb < 0.1 ? "<0.1 MB" : String(format: "%.1f MB", mb)
    }
}

public struct Dosyalar: Decodable, Equatable, Sendable {
    public let kok: String?
    public let varMi: EsnekBool?
    public let bekleyen: [BaskiDosyasi]
    public let biten: [BaskiDosyasi]

    enum CodingKeys: String, CodingKey {
        case kok, bekleyen, biten
        case varMi = "var_mi"
    }

    public var klasorVar: Bool { varMi.deger(false) }
}

// MARK: - Koç

public struct Aliskanlik: Decodable, Identifiable, Equatable, Sendable {
    public let id: Int
    public let ad: String
    public let hedef: Int?
    public let buHafta: Int?
    public let seri: Int?
    public let bugunYapildi: EsnekBool?

    enum CodingKeys: String, CodingKey {
        case id, ad, hedef, seri
        case buHafta = "bu_hafta"
        case bugunYapildi = "bugun_yapildi"
    }

    public var yapildi: Bool { bugunYapildi.deger(false) }
}

public struct AliskanlikOzeti: Decodable, Equatable, Sendable {
    public let aliskanliklar: [Aliskanlik]
}

public struct Butce: Decodable, Equatable, Sendable {
    public let toplam: Double?
    public let aylikButce: Double?
    public let kalan: Double?
    public let yuzde: Double?
    public let gunlukOrtalama: Double?
    public let aySonuTahmini: Double?

    enum CodingKeys: String, CodingKey {
        case toplam, kalan, yuzde
        case aylikButce = "aylik_butce"
        case gunlukOrtalama = "gunluk_ortalama"
        case aySonuTahmini = "ay_sonu_tahmini"
    }
}

public struct Rituel: Decodable, Equatable, Sendable {
    public let tur: String?
    public let tamamlandi: Double?
    public let veri: RituelVeri?
}

public struct RituelVeri: Decodable, Equatable, Sendable {
    public let metin: String?
    public let kaynak: String?
}

public struct KocOzeti: Decodable, Equatable, Sendable {
    public let tarih: String?
    public let sabah: Rituel?
    public let aksam: Rituel?
    public let aliskanliklar: AliskanlikOzeti?
    public let butce: Butce?
}

// MARK: - Rapor

public struct Rapor: Decodable, Equatable, Sendable {
    public let metin: String
}

// MARK: - Yazma

public struct YeniGorev: Encodable, Sendable {
    public var baslik: String
    public var tarih: String
    public var saat: String
    public var sureDk: Int
    public var projeId: Int?
    public var ayrinti: String?
    public var oncelik: Int
    public var zorunlu: Bool

    enum CodingKeys: String, CodingKey {
        case baslik, tarih, saat, ayrinti, oncelik, zorunlu
        case sureDk = "sure_dk"
        case projeId = "proje_id"
    }

    public init(baslik: String, tarih: String, saat: String,
                sureDk: Int = 60, projeId: Int? = nil,
                ayrinti: String? = nil, oncelik: Int = 2,
                zorunlu: Bool = true) {
        self.baslik = baslik
        self.tarih = tarih
        self.saat = saat
        self.sureDk = sureDk
        self.projeId = projeId
        self.ayrinti = ayrinti
        self.oncelik = oncelik
        self.zorunlu = zorunlu
    }
}

public enum Bicim {
    /// "2026-09-08" — sunucunun beklediği tarih biçimi.
    public static func tarih(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: d)
    }

    public static func saat(_ d: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "HH:mm"
        return f.string(from: d)
    }

    public static func gunAdi(_ tarih: String) -> String {
        let g = DateFormatter()
        g.locale = Locale(identifier: "en_US_POSIX")
        g.dateFormat = "yyyy-MM-dd"
        guard let d = g.date(from: tarih) else { return tarih }
        let c = DateFormatter()
        c.locale = Locale(identifier: "tr_TR")
        c.dateFormat = "d MMMM EEEE"
        return c.string(from: d)
    }
}
