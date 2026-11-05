#!/usr/bin/env python3
"""
DiamDash CRM Inventory Manager & Synchronizer
Handles real-time inventory sync from DiamDash CRM API, local caching,
and multi-attribute filtering (Shape, Carat, Measurements, Color, Clarity, Cut, etc.).
Scoped specifically to 'on_hand' store diamonds.
"""

import os
import json
import time
import urllib.request
import urllib.error
from threading import Lock

DIAMDASH_API_URL = "https://crm.diamdash.com/inventory/api/diamonds/?status=on_hand"
DIAMDASH_TOKEN = "diamdash_secure_api_token_d78f92b7c4a123eb71f98502d96"

GRADE_MAP = {
    "EX": "Excellent",
    "EXCELLENT": "Excellent",
    "ID": "Ideal",
    "IDEAL": "Ideal",
    "VG": "Very Good",
    "VERY GOOD": "Very Good",
    "GD": "Good",
    "GOOD": "Good",
    "FR": "Fair",
    "FAIR": "Fair"
}

def normalize_grade(val, default=None):
    if not val or str(val).strip().lower() in ("none", "-", "null", ""):
        return default
    v = str(val).strip().upper()
    return GRADE_MAP.get(v, str(val).strip().title())

def parse_float(val, decimals=2):
    if val is None or str(val).strip() in ("", "None", "null", "-"):
        return None
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return None

class InventoryManager:
    def __init__(self, cache_file="inventory_cache.json"):
        self.cache_file = cache_file
        self.lock = Lock()
        self.inventory = []  # List of normalized diamond records
        self.stock_index = {}  # Multi-key lookup index: stock_id / clean_id / cert_no -> record
        self.last_sync_time = None
        self.last_sync_status = "Not synced yet"
        self.load_cache()

    def sync_from_crm(self, status="on_hand", token=DIAMDASH_TOKEN, api_url=None):
        """
        Fetches active diamonds from DiamDash CRM API.
        Handles pagination, deduplication, attribute normalization, and local caching.
        Defaults to status='on_hand'.
        """
        t0 = time.time()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LUXE-TRACE-VisionEngine/1.0"
        }

        # Build initial URL with page_size=1000 for high-efficiency batch retrieval
        if api_url:
            current_url = api_url
        else:
            current_url = f"https://crm.diamdash.com/inventory/api/diamonds/?status={status}&page_size=1000"

        raw_items = []
        page_count = 0

        print(f"[Inventory Sync] Initiating DiamDash CRM sync (status={status})...")

        try:
            while current_url:
                page_count += 1
                req = urllib.request.Request(current_url, headers=headers, method="GET")

                with urllib.request.urlopen(req, timeout=25) as response:
                    if response.status != 200:
                        msg = f"CRM API returned HTTP {response.status}"
                        print(f"[Inventory Sync] {msg}")
                        self.last_sync_status = f"Error: {msg}"
                        return {"status": "error", "message": msg, "count": len(self.inventory)}

                    raw_data = response.read().decode("utf-8")
                    data = json.loads(raw_data)

                    if isinstance(data, dict):
                        page_items = data.get("results", [])
                        raw_items.extend(page_items)
                        current_url = data.get("next")
                    elif isinstance(data, list):
                        raw_items.extend(data)
                        current_url = None
                    else:
                        break

            elapsed = time.time() - t0
            print(f"[Inventory Sync] Retrieved {len(raw_items)} raw records across {page_count} page(s) in {elapsed:.2f}s.")
            res = self._process_and_save(raw_items, status_filter=status)
            res["elapsed_seconds"] = round(elapsed, 2)
            res["page_count"] = page_count
            return res

        except urllib.error.HTTPError as e:
            msg = f"HTTP Error {e.code}: {e.reason}"
            print(f"[Inventory Sync] {msg}")
            self.last_sync_status = f"Error: {msg}"
            return {"status": "error", "message": msg, "count": len(self.inventory)}
        except urllib.error.URLError as e:
            msg = f"Connection error: {e.reason}"
            print(f"[Inventory Sync] {msg}")
            self.last_sync_status = f"Error: {msg}"
            return {"status": "error", "message": msg, "count": len(self.inventory)}
        except Exception as e:
            msg = f"Unexpected exception during sync: {str(e)}"
            print(f"[Inventory Sync] {msg}")
            self.last_sync_status = f"Error: {msg}"
            return {"status": "error", "message": msg, "count": len(self.inventory)}

    def _process_and_save(self, raw_items, status_filter="on_hand"):
        """
        Deduplicates raw API records and standardizes all diamond attributes.
        Preserves all 25 requested fields:
        stock_id, cert_number, vendor_stock_id, id, sr_no, shape, ct,
        color, original_color, fancy_color, clarity, cut, polish, symm,
        fluo, lab, measurements, length, width, height, ratio, status,
        location, price_per_rate, sale_amt.
        """
        # Step 1: Deduplicate by stock_id, retaining newest updated_at record
        stock_map = {}
        for raw in raw_items:
            stock_id = str(raw.get("stock_id") or "").strip()
            if not stock_id:
                continue

            curr_updated = str(raw.get("updated_at") or "")
            if stock_id not in stock_map:
                stock_map[stock_id] = raw
            else:
                prev_updated = str(stock_map[stock_id].get("updated_at") or "")
                # Retain the record with latest updated timestamp
                if curr_updated >= prev_updated:
                    stock_map[stock_id] = raw

        # Step 2: Normalize fields
        processed = []
        new_index = {}

        for stock_id, raw in stock_map.items():
            ct_val = parse_float(raw.get("ct") or raw.get("carat"), decimals=3) or 0.0

            # Cert number standardization
            cert_no = str(raw.get("cert_number") or raw.get("certificate_no") or "").strip()

            # Shape standardization (Title Case merges e.g. "DUTCH MARQUISE" and "Dutch Marquise")
            raw_shape = raw.get("shape") or ""
            shape = raw_shape.strip().title()

            # Cut standardization (handle None gracefully without forcing fancy shapes to "Excellent")
            raw_cut = raw.get("cut")
            cut = normalize_grade(raw_cut, default=None)

            # Polish & Symmetry standardizations
            polish = normalize_grade(raw.get("polish"), default="Excellent")
            symm = normalize_grade(raw.get("symm") or raw.get("symmetry"), default="Excellent")

            # Fluorescence: fallback to "fluo"
            fluo = (raw.get("fluo") or raw.get("fluorescence") or "None").strip().title()

            # Status
            status_val = (raw.get("status") or "On Hand").strip().title()

            # Measurements and dimension floats
            length_val = parse_float(raw.get("length"), 2)
            width_val = parse_float(raw.get("width"), 2)
            height_val = parse_float(raw.get("height"), 2)
            ratio_val = parse_float(raw.get("ratio"), 2)

            # Colors
            color_val = (raw.get("color") or "").strip().upper()
            og_color = (raw.get("original_color") or "").strip().upper() or None
            fancy_col = (raw.get("fancy_color") or "").strip().upper() or None

            # Serial number
            sr_no_val = int(raw.get("sr_no")) if raw.get("sr_no") is not None else None

            normalized = {
                "id": raw.get("id"),
                "stock_id": stock_id,
                "cert_number": cert_no,
                "certificate_no": cert_no,   # Alias for backwards compatibility
                "cert_num": cert_no,         # Alias for backwards compatibility
                "vendor_stock_id": str(raw.get("vendor_stock_id") or "").strip() or None,
                "sr_no": sr_no_val,
                "shape": shape,
                "ct": ct_val,
                "carat": ct_val,             # Alias for backwards compatibility
                "color": color_val,
                "original_color": og_color,
                "fancy_color": fancy_col,
                "clarity": (raw.get("clarity") or "").strip().replace(" ", "").upper(),
                "cut": cut,
                "polish": polish,
                "symm": symm,
                "symmetry": symm,            # Alias for backwards compatibility
                "fluo": fluo,
                "fluorescence": fluo,        # Alias for backwards compatibility
                "lab": (raw.get("lab") or "").strip().upper(),
                "measurements": str(raw.get("measurements") or "").strip() or None,
                "length": length_val,
                "width": width_val,
                "height": height_val,
                "ratio": ratio_val,
                "status": status_val,
                "location": raw.get("location") or "Store",
                "price_per_rate": raw.get("price_per_rate"),
                "sale_amt": raw.get("sale_amt"),
                "updated_at": raw.get("updated_at")
            }
            processed.append(normalized)

            # Build fast multi-key lookup index for vision scanner
            new_index[stock_id] = normalized
            new_index[stock_id.lower()] = normalized
            clean_id = stock_id.replace("-", "").replace(" ", "").lower()
            if clean_id:
                new_index[clean_id] = normalized
            if cert_no:
                new_index[cert_no] = normalized
                new_index[cert_no.lower()] = normalized

        # Sort alphabetically by stock_id
        processed.sort(key=lambda x: x["stock_id"])

        with self.lock:
            self.inventory = processed
            self.stock_index = new_index
            self.last_sync_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            self.last_sync_status = f"Synced {len(processed)} on-hand items"

        # Save to local disk cache
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.inventory, f, indent=2)
            print(f"[Inventory Sync] Successfully cached {len(processed)} deduplicated on-hand diamonds to {self.cache_file}.")
        except Exception as e:
            print(f"[Inventory Sync] Warning: Failed to save cache file: {e}")

        return {
            "status": "success",
            "count": len(processed),
            "raw_count": len(raw_items),
            "status_filter": status_filter,
            "last_synced_at": self.last_sync_time
        }

    def load_cache(self):
        """Loads previously cached inventory from disk on startup."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    new_index = {}
                    for item in data:
                        sid = item.get("stock_id", "")
                        if sid:
                            new_index[sid] = item
                            new_index[sid.lower()] = item
                            clean_id = sid.replace("-", "").replace(" ", "").lower()
                            if clean_id:
                                new_index[clean_id] = item
                        cert = item.get("cert_number") or item.get("certificate_no") or item.get("cert_num")
                        if cert:
                            new_index[cert] = item
                            new_index[cert.lower()] = item

                    with self.lock:
                        self.inventory = data
                        self.stock_index = new_index
                        self.last_sync_status = f"Loaded {len(data)} cached items"
                    print(f"[Inventory Manager] Loaded {len(self.inventory)} cached items from {self.cache_file}")
            except Exception as e:
                print(f"[Inventory Manager] Failed reading cache {self.cache_file}: {e}")

    def get_item(self, code):
        """Finds diamond record by stock_id or certificate_no (case/format-insensitive)."""
        if not code:
            return None
        code_str = str(code).strip()
        with self.lock:
            if code_str in self.stock_index:
                return self.stock_index[code_str]
            clean = code_str.replace("-", "").replace(" ", "").lower()
            return self.stock_index.get(clean)

    def get_status_info(self):
        """Returns metadata about the active inventory state."""
        with self.lock:
            return {
                "count": len(self.inventory),
                "last_sync_time": self.last_sync_time,
                "last_sync_status": self.last_sync_status,
                "cache_file": self.cache_file
            }

    def get_all_items(self):
        with self.lock:
            return list(self.inventory)

    def get_filter_options(self):
        """
        Derives unique categorical values and min/max ranges for:
        - Categories: shape, color, original_color, fancy_color, clarity, cut, polish, symm, fluo, lab
        - Ranges: carat, length, width, height, ratio
        """
        with self.lock:
            if not self.inventory:
                return {
                    "shape": [], "color": [], "original_color": [], "fancy_color": [],
                    "clarity": [], "cut": [], "polish": [], "symm": [], "symmetry": [],
                    "fluo": [], "fluorescence": [], "lab": [],
                    "carat": {"min": 0.0, "max": 5.0},
                    "length": {"min": 0.0, "max": 20.0},
                    "width": {"min": 0.0, "max": 20.0},
                    "height": {"min": 0.0, "max": 10.0},
                    "ratio": {"min": 0.5, "max": 3.0}
                }

            shapes = sorted(list(set(i["shape"] for i in self.inventory if i.get("shape"))))
            colors = sorted(list(set(i["color"] for i in self.inventory if i.get("color"))))
            og_colors = sorted(list(set(i["original_color"] for i in self.inventory if i.get("original_color"))))
            fancy_colors = sorted(list(set(i["fancy_color"] for i in self.inventory if i.get("fancy_color"))))
            clarities = sorted(list(set(i["clarity"] for i in self.inventory if i.get("clarity"))))
            cuts = sorted(list(set(i["cut"] for i in self.inventory if i.get("cut"))))
            polishes = sorted(list(set(i["polish"] for i in self.inventory if i.get("polish"))))
            symms = sorted(list(set(i["symm"] for i in self.inventory if i.get("symm"))))
            fluos = sorted(list(set(i["fluo"] for i in self.inventory if i.get("fluo"))))
            labs = sorted(list(set(i["lab"] for i in self.inventory if i.get("lab"))))

            # Numeric ranges
            carats = [i["ct"] for i in self.inventory if i.get("ct") and i["ct"] > 0]
            lengths = [i["length"] for i in self.inventory if i.get("length") and i["length"] > 0]
            widths = [i["width"] for i in self.inventory if i.get("width") and i["width"] > 0]
            heights = [i["height"] for i in self.inventory if i.get("height") and i["height"] > 0]
            ratios = [i["ratio"] for i in self.inventory if i.get("ratio") and i["ratio"] > 0]

            return {
                "shape": shapes,
                "color": colors,
                "original_color": og_colors,
                "fancy_color": fancy_colors,
                "clarity": clarities,
                "cut": cuts,
                "polish": polishes,
                "symm": symms,
                "symmetry": symms,
                "fluo": fluos,
                "fluorescence": fluos,
                "lab": labs,
                "carat": {
                    "min": min(carats) if carats else 0.5,
                    "max": max(carats) if carats else 5.0
                },
                "length": {
                    "min": min(lengths) if lengths else 1.0,
                    "max": max(lengths) if lengths else 20.0
                },
                "width": {
                    "min": min(widths) if widths else 1.0,
                    "max": max(widths) if widths else 20.0
                },
                "height": {
                    "min": min(heights) if heights else 0.5,
                    "max": max(heights) if heights else 10.0
                },
                "ratio": {
                    "min": min(ratios) if ratios else 0.5,
                    "max": max(ratios) if ratios else 3.0
                }
            }

    def match_filters(self, filter_state):
        """
        Filters the inventory using multi-attribute criteria including:
        - Query (search text)
        - Categorical multi-select: shape, color, original_color, fancy_color, clarity, cut, polish, symm, fluo, lab
        - Numeric ranges: carat, length, width, height, ratio
        Returns a list of matching stock_id strings.
        """
        with self.lock:
            matched_ids = []

            # Extract search query
            query = (filter_state.get("search") or "").strip().lower()

            # Extract categorical filters (lists or sets)
            shape_filter = set(s.lower() for s in (filter_state.get("shape") or []))
            color_filter = set(c.upper() for c in (filter_state.get("color") or []))
            og_color_filter = set(c.upper() for c in (filter_state.get("original_color") or []))
            fancy_color_filter = set(c.upper() for c in (filter_state.get("fancy_color") or []))
            clarity_filter = set(cl.upper() for cl in (filter_state.get("clarity") or []))
            cut_filter = set(ct.lower() for ct in (filter_state.get("cut") or []))
            polish_filter = set(p.lower() for p in (filter_state.get("polish") or []))
            symm_filter = set(sy.lower() for sy in (filter_state.get("symm") or filter_state.get("symmetry") or []))
            fluo_filter = set(fl.lower() for fl in (filter_state.get("fluo") or filter_state.get("fluorescence") or []))
            lab_filter = set(l.upper() for l in (filter_state.get("lab") or []))

            # Numeric ranges
            min_carat = filter_state.get("minCarat") or filter_state.get("min_carat")
            max_carat = filter_state.get("maxCarat") or filter_state.get("max_carat")

            min_len = filter_state.get("minLength") or filter_state.get("min_length")
            max_len = filter_state.get("maxLength") or filter_state.get("max_length")

            min_wid = filter_state.get("minWidth") or filter_state.get("min_width")
            max_wid = filter_state.get("maxWidth") or filter_state.get("max_width")

            min_hgt = filter_state.get("minHeight") or filter_state.get("min_height")
            max_hgt = filter_state.get("maxHeight") or filter_state.get("max_height")

            min_rat = filter_state.get("minRatio") or filter_state.get("min_ratio")
            max_rat = filter_state.get("maxRatio") or filter_state.get("max_ratio")

            for item in self.inventory:
                # 1. Text Search Query Match
                if query:
                    stock_id_str = item.get("stock_id", "").lower()
                    cert_str = item.get("cert_number", "").lower()
                    shape_str = item.get("shape", "").lower()
                    vendor_id = (item.get("vendor_stock_id") or "").lower()
                    if query not in stock_id_str and query not in cert_str and query not in shape_str and query not in vendor_id:
                        continue

                # 2. Categorical multi-select filters
                if shape_filter and item.get("shape", "").lower() not in shape_filter:
                    continue
                if color_filter and item.get("color", "").upper() not in color_filter:
                    continue
                if og_color_filter and (not item.get("original_color") or item.get("original_color", "").upper() not in og_color_filter):
                    continue
                if fancy_color_filter and (not item.get("fancy_color") or item.get("fancy_color", "").upper() not in fancy_color_filter):
                    continue
                if clarity_filter and item.get("clarity", "").upper() not in clarity_filter:
                    continue
                if cut_filter and (not item.get("cut") or item.get("cut", "").lower() not in cut_filter):
                    continue
                if polish_filter and item.get("polish", "").lower() not in polish_filter:
                    continue
                if symm_filter and item.get("symm", "").lower() not in symm_filter:
                    continue
                if fluo_filter and item.get("fluo", "").lower() not in fluo_filter:
                    continue
                if lab_filter and item.get("lab", "").upper() not in lab_filter:
                    continue

                # 3. Numeric Ranges: Carat
                item_carat = item.get("ct") or item.get("carat") or 0.0
                if min_carat is not None:
                    try:
                        if item_carat < float(min_carat):
                            continue
                    except (ValueError, TypeError):
                        pass
                if max_carat is not None:
                    try:
                        if item_carat > float(max_carat):
                            continue
                    except (ValueError, TypeError):
                        pass

                # Numeric Ranges: Length
                item_len = item.get("length")
                if min_len is not None and item_len is not None:
                    try:
                        if item_len < float(min_len):
                            continue
                    except (ValueError, TypeError):
                        pass
                if max_len is not None and item_len is not None:
                    try:
                        if item_len > float(max_len):
                            continue
                    except (ValueError, TypeError):
                        pass

                # Numeric Ranges: Width
                item_wid = item.get("width")
                if min_wid is not None and item_wid is not None:
                    try:
                        if item_wid < float(min_wid):
                            continue
                    except (ValueError, TypeError):
                        pass
                if max_wid is not None and item_wid is not None:
                    try:
                        if item_wid > float(max_wid):
                            continue
                    except (ValueError, TypeError):
                        pass

                # Numeric Ranges: Height
                item_hgt = item.get("height")
                if min_hgt is not None and item_hgt is not None:
                    try:
                        if item_hgt < float(min_hgt):
                            continue
                    except (ValueError, TypeError):
                        pass
                if max_hgt is not None and item_hgt is not None:
                    try:
                        if item_hgt > float(max_hgt):
                            continue
                    except (ValueError, TypeError):
                        pass

                # Numeric Ranges: Ratio
                item_rat = item.get("ratio")
                if min_rat is not None and item_rat is not None:
                    try:
                        if item_rat < float(min_rat):
                            continue
                    except (ValueError, TypeError):
                        pass
                if max_rat is not None and item_rat is not None:
                    try:
                        if item_rat > float(max_rat):
                            continue
                    except (ValueError, TypeError):
                        pass

                matched_ids.append(item["stock_id"])

            return matched_ids
