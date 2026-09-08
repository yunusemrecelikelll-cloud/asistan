import Foundation
import UserNotifications

/// Yaklaşan görevler için bildirim.
///
/// **Yerel bildirim, sunucu itmesi değil.** APNs kurmak sertifika, anahtar
/// ve sunucuda bir itme servisi demek; karşılığında kazandığı tek şey
/// telefon kapalıyken haber verebilmek olurdu. Görevlerin saati zaten
/// önceden belli, o yüzden bildirimleri telefonun kendisi kuruyor:
/// sunucuya ulaşamasa bile çalıyor, gecikme yok, altyapı yok.
///
/// Plan değiştiğinde tümü silinip yeniden kuruluyor — sunucu tek gerçeklik
/// kaynağı, telefon yalnızca onun kopyasını taşıyor.
public actor Bildirimler {

    public static let ortak = Bildirimler()

    /// Bir görev için kaç kez dürtülecek: kaç dakika önce.
    ///
    /// Kullanıcı "sürekli darlasın" dedi. Üç kademe: hazırlan, başlama
    /// anı, ve başlamadıysan üstüne bir kez daha.
    public static let dakikalar: [Int] = [15, 0, -10]

    private let merkez = UNUserNotificationCenter.current()
    private var izinSoruldu = false

    /// Bildirim izni. İlk planlamadan önce bir kez soruluyor.
    @discardableResult
    public func izinIste() async -> Bool {
        do {
            let ok = try await merkez.requestAuthorization(
                options: [.alert, .sound, .badge])
            izinSoruldu = true
            return ok
        } catch {
            return false
        }
    }

    public func izinVar() async -> Bool {
        await merkez.notificationSettings().authorizationStatus == .authorized
    }

    /// Bugünün görevlerine göre bildirimleri baştan kur.
    ///
    /// Önce hepsini siliyoruz: ertelenen, tamamlanan ya da silinen bir
    /// görevin bildirimi çalmaya devam ederse uygulama güvenilmez oluyor.
    public func planla(_ gorevler: [Gorev]) async {
        if !izinSoruldu, await !izinVar() {
            _ = await izinIste()
        }
        guard await izinVar() else { return }

        merkez.removeAllPendingNotificationRequests()

        let simdi = Date()
        var kurulan = 0
        for g in gorevler where g.bekliyor {
            guard let an = g.zaman else { continue }
            for dk in Self.dakikalar {
                let vakit = an.addingTimeInterval(TimeInterval(-dk * 60))
                // Geçmiş bir an için bildirim kurulmaz.
                guard vakit > simdi.addingTimeInterval(5) else { continue }

                let i = UNMutableNotificationContent()
                i.title = basligi(dk)
                i.body = govde(g, dk)
                i.sound = .default
                i.interruptionLevel = dk <= 0 ? .timeSensitive : .active
                i.threadIdentifier = "gorev-\(g.id)"

                let ne = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute], from: vakit)
                let istek = UNNotificationRequest(
                    identifier: "gorev-\(g.id)-\(dk)",
                    content: i,
                    trigger: UNCalendarNotificationTrigger(dateMatching: ne,
                                                           repeats: false))
                try? await merkez.add(istek)
                kurulan += 1
                // iOS aynı anda en fazla 64 bekleyen bildirim tutuyor;
                // fazlasını sessizce atıyor. Yakın olanlar öncelikli.
                if kurulan >= 60 { return }
            }
        }
    }

    private func basligi(_ dk: Int) -> String {
        switch dk {
        case let d where d > 0: "\(d) dakika sonra"
        case 0: "Şimdi başlıyor"
        default: "Başlamadın"
        }
    }

    private func govde(_ g: Gorev, _ dk: Int) -> String {
        var s = "\(g.saat) — \(g.baslik)"
        if let p = g.projeAd, !p.isEmpty { s += " (\(p))" }
        if dk < 0 { s += "\nHâlâ bekliyor." }
        return s
    }

    public func hepsiniSil() {
        merkez.removeAllPendingNotificationRequests()
    }

    /// Kurulu bildirim sayısı — ayarlar ekranında gösteriliyor ki
    /// kullanıcı çalışıp çalışmadığını görebilsin.
    public func bekleyenSayisi() async -> Int {
        await merkez.pendingNotificationRequests().count
    }
}
