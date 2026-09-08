import NovaPaylasilan
import SwiftUI

/// Bugünün ve haftanın planı — görülebilir ve DÜZENLENEBİLİR.
///
/// Masaüstü arayüzünde olan ama telefonda hiç olmayan şeydi: kullanıcı
/// planını göremiyor, dolayısıyla telefonu yalnızca konuşmak için
/// açıyordu. Buradaki her satır dokunulabilir: başlat, tamamla, ertele,
/// sil.
struct PlanGorunumu: View {

    @StateObject private var model = PlanModeli()
    @ObservedObject private var olaylar = Olaylar.ortak
    @State private var yeniGorev = false
    /// Hafta bölümünde açık olan gün. Aynı anda tek gün açık kalıyor.
    @State private var acikGun: String?

    var body: some View {
        List {
            if let g = model.bugun {
                karneBolumu(g)
                if let s = g.siradaki { siradakiBolumu(s) }
                gorevlerBolumu(g)
            } else if model.yukleniyor {
                HStack { ProgressView(); Text("Yükleniyor…").padding(.leading, 8) }
            }
            if let h = model.hata {
                Text(h).font(.footnote).foregroundStyle(.red)
            }
            haftaBolumu
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Plan")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { yeniGorev = true } label: { Image(systemName: "plus") }
            }
        }
        .refreshable { await model.yenile() }
        .task { await model.yenile() }
        // Masaüstünde bir görev değişince telefon da tazelensin.
        .onChange(of: olaylar.sayac) { _, _ in
            if olaylar.ilgilendirir(["gorev", "plan"]) {
                Task { await model.yenile() }
            }
        }
        .sheet(isPresented: $yeniGorev) {
            GorevDuzenle(varsayilanTarih: model.bugun?.tarih
                         ?? Bicim.tarih(Date())) {
                Task { await model.yenile() }
            }
        }
    }

    // MARK: - Bölümler

    private func karneBolumu(_ g: Gun) -> some View {
        // Karne isteğe bağlı: sunucu bazı uçlarda göndermiyor. Yoksa
        // sayaçları sıfır göstermek, ekranı hiç çizmemekten iyi.
        let k = g.karne
        return Section {
            HStack(spacing: 18) {
                sayac("tamam", k?.tamam ?? 0, .green)
                sayac("kalan", k?.kalan ?? 0, .orange)
                sayac("kaçtı", k?.kacirildi ?? 0, .red)
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(g.gun).font(.subheadline.weight(.semibold))
                    Text(g.tarih).font(.caption2).foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 2)
        }
    }

    private func sayac(_ ad: String, _ n: Int, _ renk: Color) -> some View {
        VStack(spacing: 1) {
            Text("\(n)").font(.title3.weight(.semibold)).foregroundStyle(renk)
            Text(ad).font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func siradakiBolumu(_ s: Gorev) -> some View {
        Section("Sıradaki") {
            GorevSatiri(gorev: s, model: model, vurgulu: true)
        }
    }

    private func gorevlerBolumu(_ g: Gun) -> some View {
        Section("Bugün (\(g.gorevler.count))") {
            if g.gorevler.isEmpty {
                Text("Bugün için görev yok.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(g.gorevler) { gorev in
                GorevSatiri(gorev: gorev, model: model)
            }
        }
    }

    /// Haftanın günleri — açılınca O GÜNÜN İŞLERİ görünüyor.
    ///
    /// Önceden yalnızca gün adı ve iş sayısı vardı: "Çarşamba — 4 iş".
    /// Kullanıcı hangi işler olduğunu göremiyordu, yani hafta bölümü
    /// aslında hiçbir soruyu cevaplamıyordu. `/api/hafta` görevleri zaten
    /// dolu gönderiyor, ek uca gerek yok.
    ///
    /// Aynı anda tek gün açık: telefonda yedi günün hepsi açılınca liste
    /// okunmaz uzunlukta oluyor.
    private var haftaBolumu: some View {
        Section("Hafta") {
            ForEach(model.hafta?.gunler ?? []) { gun in
                DisclosureGroup(
                    isExpanded: Binding(
                        get: { acikGun == gun.tarih },
                        set: { acikGun = $0 ? gun.tarih : nil })
                ) {
                    let gorevler = gun.gorevler ?? []
                    if gorevler.isEmpty {
                        Text("Bu gün için görev yok.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    // Buradaki satırlar da tam işlevli: haftanın herhangi
                    // bir gününde kaydırarak başlat/tamamla/ertele/sil.
                    ForEach(gorevler) { g in
                        GorevSatiri(gorev: g, model: model)
                    }
                } label: {
                    haftaEtiketi(gun)
                }
            }
        }
    }

    private func haftaEtiketi(_ gun: HaftaGunu) -> some View {
        let n = gun.gorevler?.count ?? 0
        return HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text(gun.gun).font(.subheadline)
                Text(gun.tarih).font(.caption2).foregroundStyle(.tertiary)
            }
            Spacer()
            if let k = gun.karne, k.toplam > 0 {
                Text("\(k.tamam)/\(k.toplam)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(k.kacirildi > 0 ? .red : .secondary)
            } else {
                Text(n == 0 ? "boş" : "\(n) iş")
                    .font(.caption)
                    .foregroundStyle(n == 0 ? .tertiary : .secondary)
            }
        }
    }
}

/// Tek görev satırı: durum, başlık, ve kaydırmalı eylemler.
struct GorevSatiri: View {

    let gorev: Gorev
    @ObservedObject var model: PlanModeli
    var vurgulu = false

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: simge)
                .foregroundStyle(renk)
                .font(.system(size: 15))
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 2) {
                Text(gorev.baslik)
                    .font(.subheadline)
                    .strikethrough(gorev.tamam)
                    .foregroundStyle(gorev.tamam ? .secondary : .primary)
                HStack(spacing: 6) {
                    Text(gorev.saat).font(.caption.monospacedDigit())
                    if let d = gorev.sureDk { Text("\(d) dk").font(.caption2) }
                    if let p = gorev.projeAd, !p.isEmpty {
                        Text(p).font(.caption2).foregroundStyle(.tertiary)
                    }
                }
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, vurgulu ? 4 : 1)
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                Task { await model.sil(gorev) }
            } label: { Label("Sil", systemImage: "trash") }
            Button {
                Task { await model.ertele(gorev) }
            } label: { Label("Ertele", systemImage: "clock.arrow.circlepath") }
            .tint(.orange)
        }
        .swipeActions(edge: .leading) {
            if !gorev.tamam {
                Button {
                    Task { await model.tamamla(gorev) }
                } label: { Label("Tamam", systemImage: "checkmark") }
                .tint(.green)
                Button {
                    Task { await model.basla(gorev) }
                } label: { Label("Başla", systemImage: "play.fill") }
                .tint(.blue)
            }
        }
    }

    private var simge: String {
        if gorev.tamam { return "checkmark.circle.fill" }
        if gorev.kacirildi { return "exclamationmark.circle.fill" }
        if gorev.durum == "basladi" { return "play.circle.fill" }
        return "circle"
    }

    private var renk: Color {
        if gorev.tamam { return .green }
        if gorev.kacirildi { return .red }
        if gorev.durum == "basladi" { return .blue }
        return gorev.oncelik == 1 ? .orange : .secondary
    }
}
