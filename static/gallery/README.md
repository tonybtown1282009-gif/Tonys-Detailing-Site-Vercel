# Gallery photos

These images appear in two places:

1. The **"Our Work" strip** on the homepage (horizontal scroll).
2. The full grid on the **/gallery** page.

`placeholder-7.jpg` … `placeholder-34.jpg` are real customer-vehicle photos.
(The original `placeholder-1.jpg` … `placeholder-6.jpg` "Photo Coming Soon"
tiles have been removed now that real photos are live.)

| File | Recommended |
|------|-------------|
| `placeholder-7.jpg` … `placeholder-34.jpg` | JPG, 1200×900, landscape (4:3). Keep the exact same file names. |

To add more photos, drop the next `placeholder-N.jpg` file in this folder and
add a matching `<figure>` entry to both `index.html` (`#gallery .work-strip`)
and `gallery.html` (`#gallery .gal-grid`).

Photos are cached by browsers for up to an hour, so a swap can take up to an
hour to show for repeat visitors after it deploys.
