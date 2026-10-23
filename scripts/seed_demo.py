"""Seed a 'Demo Konvo' event with sample photos + example prices so you can try
the full flow without Nextcloud. Safe to re-run (clears the demo event first).

Photos are loaded from data/seed/ (run scripts/gen_samples.py first). Their
`rel_path` points at the local seed file so previews work; real events get
photos from Nextcloud via the admin Import button.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings           # noqa: E402
from app.database import db, init_db, one # noqa: E402
from app.imaging import make_previews     # noqa: E402
from app.utils import split_school_class, to_sen  # noqa: E402

SEED = ROOT / "data" / "seed"
SIZES = [("4R", '4x6"', 500, 0), ("6R", '6x8"', 900, 1),
         ("8R", '8x10"', 1500, 2), ("11R", '11x14"', 3500, 3)]


def main():
    settings.ensure_dirs()
    init_db()
    if not SEED.exists() or not any(SEED.iterdir()):
        import scripts.gen_samples as gs
        gs.main()

    with db() as conn:
        old = one(conn, "SELECT id FROM events WHERE slug=?", ("demo-konvo",))
        if old:
            conn.execute("DELETE FROM events WHERE id=?", (old["id"],))  # cascades
        eid = conn.execute(
            """INSERT INTO events(slug, name, event_date, nextcloud_folder, class_delimiter,
                   close_date, status, pickup_location, pay_bank_no, postage_west_sen, postage_east_sen)
               VALUES ('demo-konvo','Demo Konvo 2026','2026-11-15','Konvo/Demo',' - ',
                   '2026-12-31','open','SK Taman Putra','1234567890',1000,1800)""").lastrowid
        for code, label, price, sort in SIZES:
            conn.execute("INSERT INTO sizes(event_id,code,label,price_sen,sort) VALUES (?,?,?,?,?)",
                         (eid, code, label, price, sort))

        n = 0
        for class_dir in sorted(p for p in SEED.iterdir() if p.is_dir()):
            school, cls_name = split_school_class(class_dir.name, " - ")
            cid = conn.execute(
                "INSERT INTO classes(event_id,school,name,folder_path,sort) VALUES (?,?,?,?,?)",
                (eid, school, cls_name, f"Konvo/Demo/{class_dir.name}", n)).lastrowid
            for i, img in enumerate(sorted(class_dir.glob("*.jpg"))):
                made = make_previews(img.read_bytes())
                conn.execute(
                    """INSERT INTO photos(event_id,class_id,filename,rel_path,etag,
                           preview_path,thumb_path,width,height,sort)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (eid, cid, img.name, f"Konvo/Demo/{class_dir.name}/{img.name}", "seed",
                     made["preview_path"], made["thumb_path"], made["width"], made["height"], i))
                n += 1
    print(f"Seeded 'Demo Konvo' with {n} photos. Open /e/demo-konvo")


if __name__ == "__main__":
    main()
