/* icons.js — 全部内联 SVG 图标（24×24 stroke，无外部图标库/CDN） */

const P = {
  /* nav */
  sun: '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.2M12 19.2v2.2M4.7 4.7l1.6 1.6M17.7 17.7l1.6 1.6M2.6 12h2.2M19.2 12h2.2M4.7 19.3l1.6-1.6M17.7 6.3l1.6-1.6"/>',
  palette: '<path d="M12 3.2a8.8 8.8 0 1 0 0 17.6c1.5 0 2.1-.9 2.1-1.8 0-1.1-.9-1.5-.9-2.4 0-.8.6-1.3 1.5-1.3h1.6c2.2 0 3.7-1.6 3.7-3.8 0-4.5-3.6-8.3-8-8.3Z"/><circle cx="7.6" cy="11.2" r="1"/><circle cx="10.4" cy="7.5" r="1"/><circle cx="15.2" cy="8" r="1"/><circle cx="7.9" cy="15.4" r="1"/>',
  monitor: '<rect x="2.8" y="4.2" width="18.4" height="12.2" rx="2"/><path d="M8.5 20h7M12 16.4V20"/>',
  macro: '<rect x="2.6" y="5" width="18.8" height="14" rx="2.4"/><path d="M6.6 9.2h1.6M11.2 9.2h1.6M15.8 9.2h1.6M6.6 12.8h1.6M11.2 12.8h1.6M15.8 12.8h1.6M7.6 16h8.8"/>',
  keyboard: '<rect x="2.2" y="6" width="19.6" height="12" rx="2.4"/><path d="M6 9.6h.01M9.4 9.6h.01M12.8 9.6h.01M16.2 9.6h.01M19.6 9.6h.01M6 12.9h.01M9.4 12.9h.01M12.8 12.9h.01M16.2 12.9h.01M19.6 12.9h.01M7.6 16h8.8"/>',
  music: '<path d="M9 18.2V6.4l10-2v11.4"/><circle cx="6.6" cy="18.4" r="2.6"/><circle cx="16.6" cy="15.8" r="2.6"/>',
  wifi: '<path d="M2.8 8.8a14 14 0 0 1 18.4 0M5.8 12.2a10 10 0 0 1 12.4 0M8.8 15.6a6 6 0 0 1 6.4 0"/><circle cx="12" cy="19.1" r="1.1" fill="currentColor" stroke="none"/>',
  activity: '<path d="M2.8 12h4l2.4-6.4 4.4 12.8 2.4-6.4h5.2"/>',
  chip: '<rect x="4.4" y="4.4" width="15.2" height="15.2" rx="2.4"/><rect x="8.4" y="8.4" width="7.2" height="7.2" rx="1.2"/><path d="M9 2.4v2M15 2.4v2M9 19.6v2M15 19.6v2M2.4 9h2M2.4 15h2M19.6 9h2M19.6 15h2"/>',
  archive: '<rect x="2.8" y="4.6" width="18.4" height="4.2" rx="1.4"/><path d="M4.4 8.8v9.2a1.8 1.8 0 0 0 1.8 1.8h11.6a1.8 1.8 0 0 0 1.8-1.8V8.8M9.8 12.2h4.4"/>',
  settings: '<circle cx="12" cy="12" r="3.1"/><path d="M19.2 14.2a1.6 1.6 0 0 0 .32 1.76l.06.06a1.94 1.94 0 1 1-2.74 2.74l-.06-.06a1.6 1.6 0 0 0-1.76-.32 1.6 1.6 0 0 0-.96 1.46v.18a1.94 1.94 0 1 1-3.88 0v-.1a1.6 1.6 0 0 0-1.04-1.46 1.6 1.6 0 0 0-1.76.32l-.06.06a1.94 1.94 0 1 1-2.74-2.74l.06-.06a1.6 1.6 0 0 0 .32-1.76 1.6 1.6 0 0 0-1.46-.96h-.18a1.94 1.94 0 1 1 0-3.88h.1a1.6 1.6 0 0 0 1.46-1.04 1.6 1.6 0 0 0-.32-1.76l-.06-.06a1.94 1.94 0 1 1 2.74-2.74l.06.06a1.6 1.6 0 0 0 1.76.32h.08a1.6 1.6 0 0 0 .96-1.46v-.18a1.94 1.94 0 1 1 3.88 0v.1a1.6 1.6 0 0 0 .96 1.46 1.6 1.6 0 0 0 1.76-.32l.06-.06a1.94 1.94 0 1 1 2.74 2.74l-.06.06a1.6 1.6 0 0 0-.32 1.76v.08a1.6 1.6 0 0 0 1.46.96h.18a1.94 1.94 0 1 1 0 3.88h-.1a1.6 1.6 0 0 0-1.46.96Z"/>',

  /* device / status */
  plug: '<path d="M9 3v5M15 3v5M6.4 8h11.2v3.2a5.6 5.6 0 0 1-5.6 5.6 5.6 5.6 0 0 1-5.6-5.6V8ZM12 17v4"/>',
  usb: '<path d="M12 3.2v12.2"/><path d="m8.8 6.2 3.2-3 3.2 3"/><circle cx="12" cy="18.6" r="2.2"/><path d="M12 10.6 8.4 13v2.2M12 13.8l3.6-2.2v-1.4"/>',
  bluetooth: '<path d="m7 7 10 10-5 4V3l5 4L7 17"/>',
  battery: '<rect x="2.5" y="7.5" width="16" height="9" rx="2.2"/><path d="M21.4 10.6v2.8"/><rect x="4.6" y="9.6" width="6.4" height="4.8" rx="1" fill="currentColor" stroke="none"/>',
  refresh: '<path d="M20 11.4A8 8 0 0 0 6.8 5.8L4 8.4M4 4.4v4h4"/><path d="M4 12.6a8 8 0 0 0 13.2 5.6L20 15.6M20 19.6v-4h-4"/>',
  'refresh-cw': '<path d="M20 11.4A8 8 0 0 0 6.8 5.8L4 8.4M4 4.4v4h4"/><path d="M4 12.6a8 8 0 0 0 13.2 5.6L20 15.6M20 19.6v-4h-4"/>',
  power: '<path d="M12 3.4v8.2"/><path d="M7 6.4a8 8 0 1 0 10 0"/>',
  signal: '<path d="M4.4 20v-3.4M9.2 20V13M14 20V9.4M18.8 20V5.4"/>',
  mouse: '<rect x="7" y="2.6" width="10" height="18.8" rx="5"/><path d="M12 2.8v6.4"/>',

  /* ui actions */
  search: '<circle cx="10.8" cy="10.8" r="7"/><path d="m20.4 20.4-4.6-4.6"/>',
  x: '<path d="M5.4 5.4l13.2 13.2M18.6 5.4 5.4 18.6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  trash: '<path d="M3.8 6.4h16.4M9 6.4V4.2h6v2.2M5.8 6.4l.9 13a2 2 0 0 0 2 1.9h6.6a2 2 0 0 0 2-1.9l.9-13"/><path d="M10 10.4v6.6M14 10.4v6.6"/>',
  upload: '<path d="M12 16.4V4.4M7.4 9 12 4.4 16.6 9"/><path d="M4.4 15.4v3.2a2 2 0 0 0 2 2h11.2a2 2 0 0 0 2-2v-3.2"/>',
  download: '<path d="M12 4.4v12M7.4 11.8 12 16.4l4.6-4.6"/><path d="M4.4 15.4v3.2a2 2 0 0 0 2 2h11.2a2 2 0 0 0 2-2v-3.2"/>',
  image: '<rect x="3" y="4.4" width="18" height="15.2" rx="2.2"/><circle cx="8.6" cy="9.6" r="1.8"/><path d="m3.6 17.4 5-5 4.2 4.2 2.8-2.8 5.2 5.2"/>',
  play: '<path d="M7.6 4.6 19 12 7.6 19.4V4.6Z" fill="currentColor" stroke-linejoin="round"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
  'check': '<path d="m4.8 12.6 4.6 4.6L19.4 7"/>',
  'check-circle': '<circle cx="12" cy="12" r="9"/><path d="m8.2 12.2 2.6 2.6 5-5.4"/>',
  'alert-triangle': '<path d="M12 3.6 21 19.4H3L12 3.6Z"/><path d="M12 9.6v4.2M12 16.6h.01"/>',
  'alert-circle': '<circle cx="12" cy="12" r="9"/><path d="M12 7.6v5M12 16.2h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.4M12 7.8h.01"/>',
  'chevron-right': '<path d="m9.4 5.6 6.4 6.4-6.4 6.4"/>',
  'chevron-left': '<path d="M14.6 5.6 8.2 12l6.4 6.4"/>',
  'chevron-down': '<path d="m5.6 9.4 6.4 6.4 6.4-6.4"/>',
  'arrow-right': '<path d="M4.4 12h15.2M13.4 5.8 19.6 12l-6.2 6.2"/>',
  'arrow-left': '<path d="M19.6 12H4.4M10.6 5.8 4.4 12l6.2 6.2"/>',
  'arrow-up': '<path d="M12 19.4V4.6M5.8 10.8 12 4.6l6.2 6.2"/>',
  'arrow-down': '<path d="M12 4.6v14.8M5.8 13.2 12 19.4l6.2-6.2"/>',
  undo: '<path d="M4 8.6h9.4a5.6 5.6 0 0 1 0 11.2H8"/><path d="M7.8 4.4 3.6 8.6l4.2 4.2"/>',
  save: '<path d="M5 4.4h11.4L20 8v11.6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5.4a1 1 0 0 1 1-1Z"/><path d="M7.8 4.4v5.2h8V4.4M7.8 20.6v-6h8.4v6"/>',
  file: '<path d="M13.4 3.2H6.2a1.8 1.8 0 0 0-1.8 1.8v14a1.8 1.8 0 0 0 1.8 1.8h11.6a1.8 1.8 0 0 0 1.8-1.8V9.2l-6-6Z"/><path d="M13.4 3.4v5.8h5.8"/>',
  'file-json': '<path d="M13.4 3.2H6.2a1.8 1.8 0 0 0-1.8 1.8v14a1.8 1.8 0 0 0 1.8 1.8h11.6a1.8 1.8 0 0 0 1.8-1.8V9.2l-6-6Z"/><path d="M13.4 3.4v5.8h5.8M10 12.4c-1 0-1.4.6-1.4 1.6s-.4 1.4-1.2 1.4c.8 0 1.2.5 1.2 1.4s.4 1.6 1.4 1.6M14 12.4c1 0 1.4.6 1.4 1.6s.4 1.4 1.2 1.4c-.8 0-1.2.5-1.2 1.4s-.4 1.6-1.4 1.6"/>',
  shield: '<path d="M12 3 4.6 5.8v5.4c0 4.4 3 8.2 7.4 9.8 4.4-1.6 7.4-5.4 7.4-9.8V5.8L12 3Z"/><path d="m8.8 11.8 2.2 2.2 4.2-4.6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7.2V12l3.4 2"/>',
  calendar: '<rect x="3.2" y="5" width="17.6" height="16" rx="2"/><path d="M8 3v4M16 3v4M3.2 9.6h17.6"/>',
  zap: '<path d="M13.2 2.8 4.6 13.6h6l-1 7.6 8.8-11.2h-6l.8-7.2Z"/>',
  bolt: '<path d="M13.2 2.8 4.6 13.6h6l-1 7.6 8.8-11.2h-6l.8-7.2Z"/>',

  /* tools */
  paintbrush: '<path d="m14.2 4.4 5.4 5.4-8.2 8.2-5.4-5.4 8.2-8.2Z"/><path d="M10 19.4c-.6 1.2-1.6 1.8-3 2 .2-1.4-.4-2.4-3-2.6 1.8-1.6 3.4-2 4.6-.8"/>',
  eraser: '<path d="m5.8 14.6 7.4-7.4a2 2 0 0 1 2.8 0l3.4 3.4a2 2 0 0 1 0 2.8l-6 6H7.8l-2-2a2 2 0 0 1 0-2.8Z"/><path d="M10.4 20h9.4"/>',
  bucket: '<path d="m11 4.6 7.4 7.4a1.6 1.6 0 0 1 0 2.2l-4.8 4.8a1.6 1.6 0 0 1-2.2 0l-5.4-5.4a1.6 1.6 0 0 1 0-2.2l5-5.4Z"/><path d="M8.6 6.6 14 2.8M18.8 17.6c0 1.4 1 2.4 2 2.4s2-1 2-2.4c0-1.4-2-3.6-2-3.6s-2 2.2-2 3.6Z"/>',
  eyedropper: '<path d="m18.6 3.6 1.8 1.8a1.6 1.6 0 0 1 0 2.2l-2.4 2.4-4-4 2.4-2.4a1.6 1.6 0 0 1 2.2 0Z"/><path d="m14 6.4 3.6 3.6M12.4 8 4.6 15.8l-.6 4 4-.6L15.8 11.4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12.4 9 5 9-5M3 16.8l9 5 9-5"/>',
  grid: '<rect x="3.4" y="3.4" width="7" height="7" rx="1.6"/><rect x="13.6" y="3.4" width="7" height="7" rx="1.6"/><rect x="3.4" y="13.6" width="7" height="7" rx="1.6"/><rect x="13.6" y="13.6" width="7" height="7" rx="1.6"/>',
  sparkles: '<path d="M12 3.2 13.8 9l5.8 1.8-5.8 1.8L12 18.4l-1.8-5.8L4.4 10.8 10.2 9 12 3.2Z"/><path d="M18.6 15.6l.8 2.4 2.4.8-2.4.8-.8 2.4-.8-2.4-2.4-.8 2.4-.8.8-2.4Z"/>',
  snow: '<path d="M12 2.8v18.4M4 7.4l16 9.2M20 7.4 4 16.6"/><path d="m9.4 4.2 2.6 2.6 2.6-2.6M9.4 19.8l2.6-2.6 2.6 2.6M4.6 10.2l3.6-.6-.6-3.6M19.4 13.8l-3.6.6.6 3.6M4.6 13.8l3.6.6-.6 3.6M19.4 10.2l-3.6-.6.6-3.6"/>',
  flower: '<circle cx="12" cy="12" r="2.6"/><path d="M12 9.4c0-2 .4-4.4 0-6.4-.4 2 0 4.4 0 6.4ZM12 14.6c0 2-.4 4.4 0 6.4.4-2 0-4.4 0-6.4ZM9.4 12c-2 0-4.4-.4-6.4 0 2 .4 4.4 0 6.4 0ZM14.6 12c2 0 4.4.4 6.4 0-2-.4-4.4 0-6.4 0Z"/>',
  breath: '<path d="M4 8.4h12.2a2.6 2.6 0 1 0-2.4-3.6M4 12h15.6M4 15.6h10.4a2.6 2.6 0 1 1-2.4 3.6"/>',
  rainbow: '<path d="M3.4 18.6a8.6 8.6 0 0 1 17.2 0"/><path d="M6.6 18.6a5.4 5.4 0 0 1 10.8 0"/><path d="M9.8 18.6a2.2 2.2 0 0 1 4.4 0"/>',
  spring: '<path d="M12 20.6V8.2c0-2.4 3.4-2.4 3.4 0s-3.4 2.4-3.4 0V5.4c0-2.4 2.4-2.4 2.4 0"/><path d="M8.4 20.6c2 0 2.6-1.4 2.6-3.4M15.6 20.6c-1.4 0-2.4-.6-2.6-2"/>',
  flow: '<path d="M3 8.2c3.4 0 3.4 3 6.8 3s3.4-3 6.8-3 3.4 3 4.4 3M3 15.8c3.4 0 3.4-3 6.8-3s3.4 3 6.8 3 3.4-3 4.4-3"/>',
  swirl: '<path d="M12 12.2a3.4 3.4 0 1 1 3.4 3.4c-3 0-4.6-2.2-4.6-4.8 0-3.2 3-5.8 6.6-5.8 4.6 0 8 3.6 8 8.2"/><path d="M12.2 12a3.4 3.4 0 1 0-3.4 3.4c3 0 4.6-2.2 4.6-4.8C13.4 7.4 10.4 4.8 6.8 4.8c-4.6 0-8 3.6-8 8.2" transform="translate(4 1.6) scale(.92)"/>',
  split: '<path d="M12 4v6M12 14v6"/><path d="m6 8.4 4.6 3.4L6 15.2M18 8.4l-4.6 3.4L18 15.2"/>',
  ripple: '<circle cx="12" cy="12" r="2.2"/><path d="M8.4 8.4a5 5 0 0 0 0 7.2M15.6 8.4a5 5 0 0 1 0 7.2M5.2 5.2a9.6 9.6 0 0 0 0 13.6M18.8 5.2a9.6 9.6 0 0 1 0 13.6"/>',
  stream: '<path d="M3 7.4c2.2-2 4.4-2 6.6 0s4.4 2 6.6 0 3.8-1.4 4.8-.6"/><path d="M3 12.4c2.2-2 4.4-2 6.6 0s4.4 2 6.6 0 3.8-1.4 4.8-.6"/><path d="M3 17.4c2.2-2 4.4-2 6.6 0s4.4 2 6.6 0 3.8-1.4 4.8-.6"/>',
  rain: '<path d="M6.6 3.4 4.8 9M12 3.4 10.2 9M17.4 3.4 15.6 9M9.2 11.4 7 18.4M14.8 11.4 12.6 18.4M20.4 11.4 18.2 18.4"/>',
  shuttle: '<path d="M3 12h6M15 12h6"/><path d="m6 8.4-3.6 3.6L6 15.6M18 8.4l3.6 3.6L18 15.6"/><path d="M9.6 6.4 12 12l-2.4 5.6M14.4 6.4 12 12l2.4 5.6"/>',
  dot: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  eclipse: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 0 0 16Z" fill="currentColor" stroke="none"/>',
  wind: '<path d="M3.4 8.6h11.2a2.6 2.6 0 1 0-2.4-3.6M3.4 13h15.2a2.6 2.6 0 1 1-2.4 3.6M3.4 17.4h6.8"/>',
  moon: '<path d="M20.4 14.4A8.6 8.6 0 0 1 9.6 3.6a8.8 8.8 0 1 0 10.8 10.8Z"/>',
  auto: '<circle cx="12" cy="12" r="8.6"/><path d="M12 3.4v17.2"/><path d="M12 6.6a5.4 5.4 0 0 1 0 10.8Z" fill="currentColor" stroke="none"/>',
  edit: '<path d="m15.2 4.6 4.2 4.2M3.4 20.6h4.2L20.4 7.8a2 2 0 0 0 0-2.8l-1.4-1.4a2 2 0 0 0-2.8 0L3.4 16.4v4.2Z"/>',
  spinner: '<path d="M12 3.4a8.6 8.6 0 1 0 8.6 8.6" />',

  /* misc */
  list: '<path d="M8.4 6.4h12M8.4 12h12M8.4 17.6h12"/><circle cx="4.4" cy="6.4" r="1.1" fill="currentColor" stroke="none"/><circle cx="4.4" cy="12" r="1.1" fill="currentColor" stroke="none"/><circle cx="4.4" cy="17.6" r="1.1" fill="currentColor" stroke="none"/>',
  copy: '<rect x="8.4" y="8.4" width="12.2" height="12.2" rx="2"/><path d="M15.6 8.4V5.4a2 2 0 0 0-2-2H5.4a2 2 0 0 0-2 2v8.2a2 2 0 0 0 2 2h3"/>',
  folder: '<path d="M3.2 6.6a2 2 0 0 1 2-2h4l2.2 2.6h7.4a2 2 0 0 1 2 2v9.2a2 2 0 0 1-2 2H5.2a2 2 0 0 1-2-2V6.6Z"/>',
  terminal: '<rect x="2.8" y="4.2" width="18.4" height="15.6" rx="2.2"/><path d="m7 9 3 3-3 3M12.6 15.2h4.4"/>',
  code: '<path d="m8.4 7.2-5 4.8 5 4.8M15.6 7.2l5 4.8-5 4.8M13.8 4.4l-3.6 15.2"/>',
  lock: '<rect x="4.6" y="10.2" width="14.8" height="10.2" rx="2.2"/><path d="M8 10.2V7.6a4 4 0 0 1 8 0v2.6"/>',
  target: '<circle cx="12" cy="12" r="8.8"/><circle cx="12" cy="12" r="4.8"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.4 11.4a6.6 6.6 0 0 0 13.2 0M12 18v3M8.6 21h6.8"/>',
  volume: '<path d="M4.4 9.4h3.2L12 5.8v12.4l-4.4-3.6H4.4V9.4Z"/><path d="M15.4 9a4.2 4.2 0 0 1 0 6M18 6.4a7.8 7.8 0 0 1 0 11.2"/>',
  speaker: '<path d="M4.4 9.4h3.2L12 5.8v12.4l-4.4-3.6H4.4V9.4Z"/><path d="M15.4 9a4.2 4.2 0 0 1 0 6"/>',
  hash: '<path d="M5 9.4h14M5 14.6h14M10.4 3.8 8.6 20.2M15.4 3.8l-1.8 16.4"/>',
  eye: '<path d="M2.8 12S6 5.8 12 5.8 21.2 12 21.2 12 18 18.2 12 18.2 2.8 12 2.8 12Z"/><circle cx="12" cy="12" r="3"/>',
  wand: '<path d="m15 4.8 4.2 4.2M3.4 20.6 16.2 7.8l-1.8-1.8L1.6 18.8l1.8 1.8Z"/><path d="M18.4 3.4v2.8M17 4.8h2.8M8.4 4.2v2M7.4 5.2h2"/>',
};

/** 返回 SVG 字符串 */
export function icon(name, { size = 24, cls = '', stroke = 1.8 } = {}) {
  const inner = P[name] || P.info;
  return `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
}

/** 返回 SVG 元素（用于 appendChild） */
export function iconEl(name, opts) {
  const tpl = document.createElement('template');
  tpl.innerHTML = icon(name, opts).trim();
  return tpl.content.firstElementChild;
}

/** 品牌 logo：迷你键盘 */
export function brandLogo(size = 22) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <rect x="3" y="8" width="26" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="2"/>
    <g fill="currentColor">
      <rect x="6" y="11" width="4" height="4" rx="1"/><rect x="12" y="11" width="4" height="4" rx="1"/>
      <rect x="18" y="11" width="4" height="4" rx="1"/><rect x="24" y="11" width="2.4" height="4" rx="1"/>
      <rect x="6" y="17" width="5" height="4" rx="1"/><rect x="13" y="17" width="11" height="4" rx="1"/>
    </g>
  </svg>`;
}

export const ICON_NAMES = Object.keys(P);
