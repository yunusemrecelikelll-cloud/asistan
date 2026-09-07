import XCTest
@testable import NovaPaylasilan

/// Protokol ve WAV çözme testleri.
///
/// Ses donanımı gerektiren şeyler burada sınanmıyor (simülatörde
/// güvenilmez); sınanan şey baytların doğru yorumlanması. Sunucu tarafındaki
/// `testler/test_akis.py` ile birlikte protokolün iki ucunu da kilitliyor.
final class ProtokolTestleri: XCTestCase {

    private func coz(_ sozluk: [String: Any]) -> Protokol.Gelen? {
        let d = try! JSONSerialization.data(withJSONObject: sozluk)
        return Protokol.Gelen.coz(d)
    }

    func testHazirCozuluyor() {
        guard case .hazir(let ses)? = coz(["tur": "hazir", "ses": "ses2"])
        else { return XCTFail("hazir çözülmedi") }
        XCTAssertEqual(ses, "ses2")
    }

    func testKismiYanitIsaretleniyor() {
        guard case .yanit(let m, _, let kismi, _)? =
                coz(["tur": "yanit", "metin": "Merhaba", "kismi": true])
        else { return XCTFail("yanit çözülmedi") }
        XCTAssertEqual(m, "Merhaba")
        XCTAssertTrue(kismi, "kısmi yanıt ilk cümledir; ekranda güncellenmeli")
    }

    func testTamYanitKismiDegil() {
        guard case .yanit(_, _, let kismi, _)? =
                coz(["tur": "yanit", "metin": "Bitti"])
        else { return XCTFail("yanit çözülmedi") }
        XCTAssertFalse(kismi)
    }

    func testOlayIcIceCozuluyor() {
        // Sunucu olayı {"tur":"olay","olay":{...}} olarak yolluyor. Düz
        // yayılsaydı olayın kendi "tur" alanı dıştakini ezerdi; "bitti"
        // adlı bir olay turu erkenden kapatırdı.
        guard case .olay(let tur, let veri)? = coz(
            ["tur": "olay",
             "olay": ["tur": "gorev", "id": 7, "gorev_id": 3]])
        else { return XCTFail("olay çözülmedi") }
        XCTAssertEqual(tur, "gorev")
        XCTAssertEqual(veri["gorev_id"] as? Int, 3)
    }

    func testBilinmeyenCerceveYokSayiliyor() {
        // Protokole yeni bir çerçeve türü eklendiğinde eski istemci
        // çökmemeli; onu olay sanmamalı da.
        XCTAssertNil(coz(["tur": "bilinmeyen_bir_sey"]))
    }

    func testBozukVeriNilDonuyor() {
        XCTAssertNil(Protokol.Gelen.coz(Data("bu json değil".utf8)))
    }

    func testGidenCerceveler() {
        func alanlar(_ m: Protokol.Giden) -> [String: Any] {
            (try? JSONSerialization.jsonObject(with: m.kodla()))
                as? [String: Any] ?? [:]
        }
        XCTAssertEqual(alanlar(.giris(belirtec: "abc"))["tur"] as? String,
                       "giris")
        XCTAssertEqual(alanlar(.giris(belirtec: "abc"))["belirtec"] as? String,
                       "abc")
        let ses = alanlar(.sesBitti(uzanti: ".pcm", sesli: true))
        XCTAssertEqual(ses["uzanti"] as? String, ".pcm",
                       "ham PCM gönderiyoruz; başlığı sunucu ekliyor")
    }

    // MARK: - WAV

    private func ornekWav(oran: Int = 24_000, kanal: Int = 1,
                          ornekler: [Int16]) -> Data {
        var govde = Data()
        for o in ornekler {
            govde.append(contentsOf: withUnsafeBytes(of: o.littleEndian) {
                Array($0)
            })
        }
        return SesKayit.wavBasligi(veriUzunlugu: govde.count, oran: oran,
                                   kanal: kanal) + govde
    }

    func testWavCozuluyor() {
        let veri = ornekWav(ornekler: [0, 16384, -16384, 32767])
        guard let (bicim, tampon) = SesCalar.wavCoz(veri) else {
            return XCTFail("WAV çözülmedi")
        }
        XCTAssertEqual(bicim.sampleRate, 24_000)
        XCTAssertEqual(tampon.frameLength, 4)
        let k = tampon.floatChannelData![0]
        XCTAssertEqual(k[0], 0, accuracy: 0.001)
        XCTAssertEqual(k[1], 0.5, accuracy: 0.001)
        XCTAssertEqual(k[2], -0.5, accuracy: 0.001)
    }

    func testKisaVeriReddediliyor() {
        XCTAssertNil(SesCalar.wavCoz(Data(repeating: 0, count: 20)))
    }

    func testRiffOlmayanReddediliyor() {
        var veri = ornekWav(ornekler: [0, 1, 2, 3])
        veri.replaceSubrange(0..<4, with: Data("XXXX".utf8))
        XCTAssertNil(SesCalar.wavCoz(veri))
    }

    func testAradaBaskaObekVarkenCozuluyor() {
        // XTTS'in ürettiği WAV'larda fmt ile data arasında LIST öbeği
        // olabiliyor; sabit 44 bayt varsaymak cızırtıya yol açıyordu.
        let temel = ornekWav(ornekler: [0, 16384, -16384, 32767])
        var yeni = temel.prefix(36)                    // RIFF + fmt
        var ek = Data("LIST".utf8)
        ek.append(contentsOf: withUnsafeBytes(of: UInt32(4).littleEndian) {
            Array($0)
        })
        ek.append(contentsOf: [1, 2, 3, 4])
        yeni.append(ek)
        yeni.append(temel.suffix(from: 36))            // data öbeği
        guard let (_, tampon) = SesCalar.wavCoz(Data(yeni)) else {
            return XCTFail("araya öbek girince çözülemedi")
        }
        XCTAssertEqual(tampon.frameLength, 4)
    }

    func testWavBasligiDogruBoyutYaziyor() {
        let baslik = SesKayit.wavBasligi(veriUzunlugu: 1000)
        XCTAssertEqual(baslik.count, 44)
        let riffBoy = baslik.withUnsafeBytes {
            $0.loadUnaligned(fromByteOffset: 4, as: UInt32.self)
        }
        XCTAssertEqual(UInt32(littleEndian: riffBoy), 1036)
    }
}
