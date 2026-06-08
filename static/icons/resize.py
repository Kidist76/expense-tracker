from PIL import Image
img = Image.open('icon-512.png')
for s in [72, 96, 128, 144, 152, 192]:
    img.resize((s, s), Image.Resampling.LANCZOS).save(f'icon-{s}.png')
    print(f'Done: icon-{s}.png')
print('All icons resized!')
