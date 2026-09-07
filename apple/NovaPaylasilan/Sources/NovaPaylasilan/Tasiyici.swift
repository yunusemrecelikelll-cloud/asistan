import Foundation

/// Çerçeveleri taşıyan alt katman.
///
/// Neden soyutlandı: telefon bilgisayara doğrudan WebSocket'le bağlanıyor,
/// saat ise ev ağının dışındayken telefon üzerinden geçmek zorunda
/// (Tailscale'in watchOS istemcisi yok). Protokolün kendisi iki durumda da
/// aynı; değişen yalnızca baytların hangi borudan aktığı. Ayırınca
/// `NovaBaglanti` ve `Oturum` her iki uygulamada da kelimesi kelimesine
/// aynı kodla çalışıyor.
public protocol Tasiyici: AnyObject {
    /// Sunucudan gelen JSON çerçevesi.
    var metinGeldi: ((Data) -> Void)? { get set }
    /// Sunucudan gelen ikili ses çerçevesi.
    var ikiliGeldi: ((Data) -> Void)? { get set }
    /// Taşıyıcının kendi durumu değişti.
    var durumDegisti: ((TasiyiciDurumu) -> Void)? { get set }

    func ac()
    func kapat()
    func yolla(_ veri: Data)
    func ikiliYolla(_ veri: Data)

    /// Kullanıcıya gösterilen kısa ad ("doğrudan", "telefon üzerinden").
    var ad: String { get }

    /// Bu taşıyıcı sunucuyla DOĞRUDAN mı konuşuyor?
    ///
    /// Saat röle üzerinden geçiyor: kimlik doğrulamayı ve nabzı telefon
    /// kendi bağlantısında zaten yapıyor. Saatin ayrıca belirteç yollaması
    /// (ki saatte belirteç yok) ya da nabız üretmesi hem gereksiz hem de
    /// WatchConnectivity üzerinde boşuna trafik.
    var sunucuyaDogrudan: Bool { get }
}

public extension Tasiyici {
    var sunucuyaDogrudan: Bool { true }
}

public enum TasiyiciDurumu: Equatable {
    case kapali
    case acilliyor
    case acik
    case hata(String)
}
