# QR Price Finder

Sorani QR scanner + Flask server. The browser scans a QR code; the cloud server fetches the public product page and looks for product prices in JSON-LD or common price metadata.

## Deploy on Render (free tier)
1. Upload all files and the `templates` folder to your GitHub repository. Keep the folder name exactly `templates`.
2. In Render, choose **New + → Blueprint** and connect the repository.
3. Render detects `render.yaml`. Create the service.
4. Wait for deployment, then open the `onrender.com` URL using HTTPS.
5. Allow camera permission. Scan a QR code.

## Important limitations
- No scraper can reliably read prices from every website. Some sites require login, JavaScript rendering, region selection, cookies, or block automated requests.
- This version reads common structured product data (JSON-LD) and metadata. It does not bypass logins, paywalls, CAPTCHAs, or anti-bot protections.
- The returned price is shown in the site's original currency. Currency conversion to IQD is not enabled because it requires a trusted live exchange-rate source.
- Camera access requires HTTPS (Render provides HTTPS).

## Local test
```bash
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Safety
The server rejects non-public/local network addresses and rechecks redirects to reduce server-side request forgery risk. Do not remove these checks.
