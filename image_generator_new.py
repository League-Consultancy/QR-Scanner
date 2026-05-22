import zxingcpp
import numpy as np
from PIL import Image

# CONFIG
NUM_CODES = 40

IMG_WIDTH = 4961
IMG_HEIGHT = 7016

COLS = 5
ROWS = 8

MARGIN_X = 2
MARGIN_Y = 2


def generate_barcode(data: str, target_w: int, target_h: int):

    # Generate barcode WITHOUT forcing huge dimensions
    result = zxingcpp.write_barcode(
        format=zxingcpp.BarcodeFormat.DataMatrix,
        text=data,
        quiet_zone=2
    )

    arr = np.array(result)

    # Convert to PIL
    img = Image.fromarray(arr)

    # Compute integer scaling factor
    scale_x = target_w // img.width
    scale_y = target_h // img.height

    scale = max(1, min(scale_x, scale_y))

    new_w = img.width * scale
    new_h = img.height * scale

    # IMPORTANT:
    # Use NEAREST to preserve sharp barcode edges
    img = img.resize((new_w, new_h), Image.NEAREST)

    return img


def main():

    canvas = Image.new("L", (IMG_WIDTH, IMG_HEIGHT), 255)

    cell_width = IMG_WIDTH // COLS
    cell_height = IMG_HEIGHT // ROWS

    code_width = cell_width - MARGIN_X
    code_height = cell_height - MARGIN_Y

    count = 560

    for r in range(ROWS):
        for c in range(COLS):

            data = f"{count:08d}"

            img = generate_barcode(
                data,
                code_width,
                code_height
            )

            x = c * cell_width + (cell_width - img.width) // 2
            y = r * cell_height + (cell_height - img.height) // 2

            canvas.paste(img, (x, y))

            count += 1

    canvas.save("datamatrix_fixed_560-599.png")

    print("Saved datamatrix_fixed.png")


if __name__ == "__main__":
    main()