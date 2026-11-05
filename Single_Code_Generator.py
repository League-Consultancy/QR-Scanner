#!/usr/bin/env python3
"""Generate a single Data Matrix label as a PNG image.

Canvas: 45 x 45 mm
Data Matrix graphic: fitted within 35 x 35 mm
The Data Matrix encodes only the Stock ID.
Text fields are printed below the code.
"""

from pathlib import Path
import argparse
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import zxingcpp

DEFAULT_LABEL_WIDTH_MM = 40.0
DEFAULT_LABEL_HEIGHT_MM = 60.0
DEFAULT_CODE_AREA_MM = 35.0
QUIET_ZONE = 2
DPI = 300

FIELDS = (
    "stock_id",
    "shape",
    "carat",
    "color",
    "clarity",
    "lab",
    "certificate_no",
)


def barcode_to_pil(barcode):
    """Convert zxingcpp output to a high-contrast grayscale PIL image."""
    if isinstance(barcode, Image.Image):
        image = barcode
    else:
        image = Image.fromarray(np.asarray(barcode))
    return image.convert("L").point(lambda p: 0 if p < 128 else 255)


def load_font(size_px):
    font_paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size=size_px)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size_px)
    except Exception:
        return ImageFont.load_default()


def fit_text(draw, text, max_width_px, initial_size_px):
    """Shrink text only if necessary to fit the label width."""
    size = max(10, initial_size_px)
    font = load_font(size)
    while size > 10 and draw.textbbox((0, 0), text, font=font)[2] > max_width_px:
        size -= 1
        font = load_font(size)
    return font


def make_png(
    fields,
    output_path,
    label_width_mm=DEFAULT_LABEL_WIDTH_MM,
    label_height_mm=DEFAULT_LABEL_HEIGHT_MM,
    code_width_mm=None,
    code_height_mm=None,
    dpi=DPI,
    show_text=True,
):
    stock_id = str(fields.get("stock_id", "")).strip()
    if not stock_id:
        raise ValueError("Stock ID cannot be empty.")

    # Determine code area dimensions if not explicitly provided
    if code_width_mm is None and code_height_mm is None:
        if show_text and label_height_mm > 15:
            # Leave room for text lines at the bottom (~9-10 mm for text and margins)
            text_reserve_mm = min(10.0, label_height_mm * 0.25)
            available_h = max(5.0, label_height_mm - text_reserve_mm - 1.0)
            available_w = label_width_mm * 0.9
            code_side = min(available_w, available_h)
            code_width_mm = code_side
            code_height_mm = code_side
        else:
            code_side = min(label_width_mm * 0.9, label_height_mm * 0.9)
            code_width_mm = code_side
            code_height_mm = code_side
    elif code_width_mm is None:
        code_width_mm = min(label_width_mm * 0.9, code_height_mm)
    elif code_height_mm is None:
        code_height_mm = min(label_height_mm * 0.9, code_width_mm)

    # Only Stock ID is encoded in the Data Matrix.
    try:
        barcode = zxingcpp.write_barcode(
            format=zxingcpp.BarcodeFormat.DataMatrix,
            text=stock_id,
            quiet_zone=QUIET_ZONE,
        )
    except AttributeError:
        barcode = zxingcpp.create_barcode(
            format=zxingcpp.BarcodeFormat.DataMatrix,
            text=stock_id,
            quiet_zone=QUIET_ZONE,
        )
    code_img = barcode_to_pil(barcode)

    # Convert mm to pixels at the requested print resolution.
    px_per_mm = dpi / 25.4
    label_w_px = round(label_width_mm * px_per_mm)
    label_h_px = round(label_height_mm * px_per_mm)
    code_area_w_px = round(code_width_mm * px_per_mm)
    code_area_h_px = round(code_height_mm * px_per_mm)

    # Scale the barcode image to fit within the designated code area while preserving aspect ratio
    scale = min(code_area_w_px / code_img.width, code_area_h_px / code_img.height)
    target_w = max(1, round(code_img.width * scale))
    target_h = max(1, round(code_img.height * scale))
    code_img = code_img.resize((target_w, target_h), Image.Resampling.NEAREST)

    canvas = Image.new("RGB", (label_w_px, label_h_px), "white")
    draw = ImageDraw.Draw(canvas)

    lines = [
        f"ID: {fields.get('stock_id', '')} | Shape: {fields.get('shape', '')}",
        f"Carat: {fields.get('carat', '')} | Color: {fields.get('color', '')} | Clarity: {fields.get('clarity', '')}",
        f"Lab: {fields.get('lab', '')} | Cert: {fields.get('certificate_no', '')}",
    ]

    margin_px = round(1.0 * px_per_mm)
    max_text_width = max(10, label_w_px - 2 * margin_px)

    code_x = (label_w_px - code_img.width) // 2

    # Check if there is room for text lines below the barcode
    remaining_h_for_text = label_h_px - code_img.height
    min_text_h_needed = round(5.0 * px_per_mm)

    if show_text and remaining_h_for_text >= min_text_h_needed:
        # Place barcode near top margin, text below
        top_margin_px = round(0.5 * px_per_mm)
        code_y = top_margin_px
        canvas.paste(code_img.convert("RGB"), (code_x, code_y))

        # Start text directly below the code with a neat margin
        gap_after_code_px = round(1.5 * px_per_mm)
        text_start_y_px = code_y + code_img.height + gap_after_code_px
        available_text_h_px = label_h_px - text_start_y_px - margin_px

        # Calculate readable font size to fit both width and available vertical space
        # Aim for ~2.5 - 2.8 mm font height, scaled to fit lines and width
        target_font_size = round(min(available_text_h_px / (len(lines) * 1.15), 2.8 * px_per_mm))
        target_font_size = max(11, target_font_size)

        # Fit all lines with consistent readable font size
        fitted_fonts = [fit_text(draw, line, max_text_width, target_font_size) for line in lines]
        # Use the smallest fitted font size across lines to maintain visual consistency
        min_size = min(getattr(f, "size", target_font_size) for f in fitted_fonts)
        chosen_font = load_font(min_size)

        # Measure text line height
        sample_bbox = draw.textbbox((0, 0), "Ay|0123456789", font=chosen_font)
        line_height_px = sample_bbox[3] - sample_bbox[1]
        line_spacing_px = round(line_height_px * 1.12)  # Tight spacing, no excessive gap

        current_y_px = text_start_y_px
        for text in lines:
            draw.text(
                (label_w_px // 2, current_y_px),
                text,
                fill="black",
                font=chosen_font,
                anchor="mt",  # Top-aligned for precise line-to-line packing
            )
            current_y_px += line_spacing_px
    else:
        # Center code vertically if no text or insufficient space
        code_y = (label_h_px - code_img.height) // 2
        canvas.paste(code_img.convert("RGB"), (code_x, code_y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", dpi=(dpi, dpi), optimize=True)

    print(f"Saved PNG: {output_path}")
    print(f"Canvas: {label_width_mm:g} x {label_height_mm:g} mm at {dpi} DPI ({label_w_px} x {label_h_px} pixels)")
    print(f"Barcode Area: {code_width_mm:g} x {code_height_mm:g} mm (actual code: {target_w}x{target_h} px)")
    print(f"Stock ID encoded in Data Matrix: {stock_id}")
    if show_text and remaining_h_for_text >= min_text_h_needed:
        print("Printed fields: Stock ID, Shape, Carat, Color, Clarity, Lab, Certificate No.")
    print("Print at 100% / actual size and test scanning before production.")


def main():
    parser = argparse.ArgumentParser(description="Generate one Data Matrix label as PNG with flexible dimensions.")
    parser.add_argument("--stock-id", default="STOCK-001")
    parser.add_argument("--shape", default="Round")
    parser.add_argument("--carat", default="1.00")
    parser.add_argument("--color", default="D")
    parser.add_argument("--clarity", default="VVS1")
    parser.add_argument("--lab", default="IGI")
    parser.add_argument("--certificate-no", default="123456789")
    parser.add_argument("--output", default="single_datamatrix_label.png")
    parser.add_argument("--dpi", type=int, default=DPI, help="Output resolution (default: 300)")

    # Flexible dimensions
    parser.add_argument("--width", "--label-width", type=float, default=DEFAULT_LABEL_WIDTH_MM,
                        help=f"Canvas/Box width in mm (default: {DEFAULT_LABEL_WIDTH_MM})")
    parser.add_argument("--height", "--label-height", type=float, default=DEFAULT_LABEL_HEIGHT_MM,
                        help=f"Canvas/Box height in mm (default: {DEFAULT_LABEL_HEIGHT_MM})")
    parser.add_argument("--code-width", type=float, default=None,
                        help="Data Matrix max width in mm (default: auto)")
    parser.add_argument("--code-height", type=float, default=None,
                        help="Data Matrix max height in mm (default: auto)")
    parser.add_argument("--no-text", action="store_true", help="Omit text lines and center the Data Matrix")

    args = parser.parse_args()

    fields = {
        "stock_id": args.stock_id,
        "shape": args.shape,
        "carat": args.carat,
        "color": args.color,
        "clarity": args.clarity,
        "lab": args.lab,
        "certificate_no": args.certificate_no,
    }
    make_png(
        fields=fields,
        output_path=Path(args.output),
        label_width_mm=args.width,
        label_height_mm=args.height,
        code_width_mm=args.code_width,
        code_height_mm=args.code_height,
        dpi=args.dpi,
        show_text=not args.no_text,
    )


if __name__ == "__main__":
    main()
