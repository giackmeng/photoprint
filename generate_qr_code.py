import qrcode

url = "http://192.168.1.50:5000/?event=GIULIA-MARCO-2026"

img = qrcode.make(url)
img.save("event_qr.png")

print("QR generato: event_qr.png")