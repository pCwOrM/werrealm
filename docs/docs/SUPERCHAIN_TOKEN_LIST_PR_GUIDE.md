# Optimism & Base Superchain Token List PR Rehberi

Bu rehber, **Werrium ($WERR)** tokenını Base ve Optimism ekosisteminin resmi token kayıt defteri olan **Superchain Token List**'e eklemek için hazırlanmıştır.

PR merge edildiğinde:
1. **Safe (`app.safe.global`)**: Sarı "Suspicious / Unverified" uyarısı kalkar, yerini resmi doğrulanmış onay rozeti ve logo alır.
2. **Uniswap & DEX'ler**: Sözleşme adresi aramadan `$WERR` adı doğrudan çıkar.
3. **MetaMask & Web3 Cüzdanları**: Token logosu ve bakiyesi otomatik tanınır.

---

## 1. Hazırlanan Dosyalar
Depomuzda hazır bulunan klasör:
`werrealm/superchain_tokenlist/data/WERR/`

İçindeki dosyalar:
1. **`data.json`**:
```json
{
  "name": "Werrium",
  "symbol": "WERR",
  "decimals": 18,
  "description": "Werrium ($WERR) is the sovereign utility token of the Werrealm ecosystem, powering AI oracle inference, computational staking, and autonomic reflex burning on Base.",
  "website": "https://werrealm.network",
  "twitter": "@pcw0rm",
  "nobridge": true,
  "tokens": {
    "base": {
      "address": "0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2"
    }
  }
}
```
2. **`logo.svg`**: Werrium 32x32 vektörel nöral-biyomimetik W logosu.

---

## 2. GitHub Üzerinden PR Açma Adımları (2 Dakika)

1. **Depoyu Açın:**
   [https://github.com/ethereum-optimism/ethereum-optimism.github.io](https://github.com/ethereum-optimism/ethereum-optimism.github.io) adresine gidin.

2. **Fork Edin:**
   Sağ üstteki **"Fork"** butonuna tıklayarak depoyu kendi GitHub hesabınıza (`pCwOrM`) kopyalayın.

3. **Dosyaları Yükleyin:**
   Fork ettiğiniz depoda `data/` klasörüne girin:
   - Sağ üstteki **"Add file" -> "Upload files"** seçin.
   - Yerel bilgisayarınızdaki `werrealm/superchain_tokenlist/data/WERR` klasörünü (veya içindeki `data.json` ve `logo.svg` dosyalarını `data/WERR/` yoluna) sürükleyip bırakın.
   - Commit mesajı olarak: `Add Werrium (WERR) on Base` yazıp **Commit changes** deyin.

4. **Pull Request (PR) Oluşturun:**
   - Depo sayfasında en üstte çıkan **"Contribute" -> "Open pull request"** butonuna tıklayın.
   - PR Başlığı: `Add Werrium (WERR) on Base`
   - PR Açıklaması:
     ```markdown
     ### Token Addition Details

     - **Token Name:** Werrium
     - **Symbol:** WERR
     - **Decimals:** 18
     - **Chain:** Base Mainnet (Chain ID 8453)
     - **Address:** 0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2
     - **Website:** https://werrealm.network
     - **Explorer:** https://basescan.org/token/0xFfa2c95b68B76af00FBD84295cBA5e5268a996d2
     - **Bridge:** Native Base deployment (nobridge: true)
     ```
   - **Create Pull Request** butonuna basın.

5. **Otomatik Kontroller (CI):**
   Optimism CI botu otomatik olarak adresi, zinciri ve on-chain parametreleri doğrulayacak ve PR'ı inceleme kuyruğuna alacaktır.
