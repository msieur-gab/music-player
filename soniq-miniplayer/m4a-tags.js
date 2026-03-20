/**
 * Lightweight m4a/mp4 tag reader.
 * Parses MP4 atoms to extract title, artist, album, and cover art.
 */

/**
 * Read metadata from an m4a File or Blob.
 * Returns { title, artist, album, cover: Blob|null }
 */
export async function readM4ATags(file) {
  const buf = await file.arrayBuffer();
  const view = new DataView(buf);
  const result = { title: '', artist: '', album: '', cover: null };

  try {
    const moov = findBox(view, 0, buf.byteLength, 'moov');
    if (!moov) return result;

    const udta = findBox(view, moov.start, moov.end, 'udta');
    if (!udta) return result;

    const meta = findMeta(view, udta.start, udta.end);
    if (!meta) return result;

    const ilst = findBox(view, meta.start, meta.end, 'ilst');
    if (!ilst) return result;

    // Iterate ilst children
    let offset = ilst.start;
    while (offset < ilst.end) {
      const size = view.getUint32(offset);
      if (size < 8) break;
      const type = getString(view, offset + 4, 4);
      const boxEnd = offset + size;

      // Look for 'data' sub-box inside each ilst item
      const data = findBox(view, offset + 8, boxEnd, 'data');
      if (data) {
        // data box: 4 bytes version/flags, 4 bytes locale, then payload
        const flags = view.getUint32(data.start) & 0xFFFFFF;
        const payload = data.start + 8;
        const payloadLen = data.end - payload;

        if (payloadLen > 0) {
          switch (type) {
            case '\xA9nam': // ©nam — title
              result.title = new TextDecoder().decode(new Uint8Array(buf, payload, payloadLen)).trim();
              break;
            case '\xA9ART': // ©ART — artist
              result.artist = new TextDecoder().decode(new Uint8Array(buf, payload, payloadLen)).trim();
              break;
            case '\xA9alb': // ©alb — album
              result.album = new TextDecoder().decode(new Uint8Array(buf, payload, payloadLen)).trim();
              break;
            case 'covr': // cover art
              const mimeType = flags === 14 ? 'image/png' : 'image/jpeg';
              result.cover = new Blob([new Uint8Array(buf, payload, payloadLen)], { type: mimeType });
              break;
          }
        }
      }

      offset = boxEnd;
    }
  } catch (e) {
    // Parsing failed — return what we have
  }

  return result;
}

// ── Box navigation helpers ──

function getString(view, offset, len) {
  let s = '';
  for (let i = 0; i < len; i++) s += String.fromCharCode(view.getUint8(offset + i));
  return s;
}

function findBox(view, start, end, type) {
  let offset = start;
  while (offset < end - 8) {
    const size = view.getUint32(offset);
    if (size < 8) break;
    const boxType = getString(view, offset + 4, 4);
    const boxEnd = offset + size;
    if (boxEnd > end) break;
    if (boxType === type) {
      return { start: offset + 8, end: boxEnd };
    }
    offset = boxEnd;
  }
  return null;
}

function findMeta(view, start, end) {
  // 'meta' box has a 4-byte version/flags field before children
  let offset = start;
  while (offset < end - 8) {
    const size = view.getUint32(offset);
    if (size < 8) break;
    const boxType = getString(view, offset + 4, 4);
    const boxEnd = offset + size;
    if (boxEnd > end) break;
    if (boxType === 'meta') {
      // Skip 4 bytes version/flags
      return { start: offset + 12, end: boxEnd };
    }
    offset = boxEnd;
  }
  return null;
}
