"""A realistic dense screenshot (editor + terminal traceback) to test image reading."""
import sys

from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1]
img = Image.new("RGB", (1920, 1080), (30, 30, 30))
d = ImageDraw.Draw(img)
mono = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 16)
ui = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
d.rectangle((0, 0, 1920, 34), fill=(50, 50, 52))
d.text((12, 8), "sync_sheet.py - job-tools - Visual Studio Code", font=ui, fill=(210, 210, 210))
code = r'''import gspread
from tracker import load_rows

def push(rows, sheet_id="1AbC_demo"):
    gc = gspread.service_account(filename="creds.json")
    ws = gc.open_by_key(sheet_id).worksheet("Applied")
    ws.update("A2", [[r.company, r.role, r.date] for r in rows])

if __name__ == "__main__":
    push(load_rows("job_search_tracker.csv"))'''.splitlines()
for i, line in enumerate(code):
    d.text((70, 60 + i * 22), line, font=mono, fill=(212, 212, 212))
    d.text((30, 60 + i * 22), str(i + 1), font=mono, fill=(120, 120, 120))
d.rectangle((0, 640, 1920, 1080), fill=(24, 24, 24))
d.text((20, 650), "TERMINAL", font=ui, fill=(180, 180, 180))
tb = r'''PS C:\Users\demo\job-tools> python sync_sheet.py
Traceback (most recent call last):
  File "C:\Users\demo\job-tools\sync_sheet.py", line 10, in <module>
    push(load_rows("job_search_tracker.csv"))
  File "C:\Users\demo\job-tools\sync_sheet.py", line 6, in push
    ws = gc.open_by_key(sheet_id).worksheet("Applied")
  File "C:\Python315\Lib\site-packages\gspread\spreadsheet.py", line 388, in worksheet
    raise WorksheetNotFound(title)
gspread.exceptions.WorksheetNotFound: Applied'''.splitlines()
for i, line in enumerate(tb):
    d.text((20, 690 + i * 22), line, font=mono, fill=(230, 120, 120) if i else (200, 200, 200))
img.save(out + "/code.png")
for side in (1024, 1280, 1568):
    im = img.copy()
    im.thumbnail((side, side), Image.LANCZOS)
    im.save(f"{out}/code_{side}.jpg", quality=85)
    print(side, im.size)
