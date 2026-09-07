import NovaPaylasilan
import SwiftUI

@main
struct NovaTelefonApp: App {

    @StateObject private var oturum = Oturum()
    @StateObject private var role = SaatRolesi()
    @Environment(\.scenePhase) private var evre

    var body: some Scene {
        WindowGroup {
            AnaGorunum()
                .environmentObject(oturum)
                .environmentObject(role)
                .onAppear { oturum.basla() }
                .onChange(of: evre) { _, yeni in
                    // Uygulama arkaya alınınca iOS soketi er geç kapatıyor.
                    // Öne gelir gelmez yeniden bağlanıyoruz ki kullanıcı
                    // telefonu açtığı an konuşabilsin, önce beklemesin.
                    if yeni == .active { oturum.basla() }
                }
        }
    }
}
