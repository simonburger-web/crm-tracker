// Builds crm/static/crm/app.css for the CRM pages (the gym section has its own inline styles).
// Rebuild after changing classes in templates:
//   npx tailwindcss@3 -c tailwind/tailwind.config.js -i tailwind/input.css -o crm/static/crm/app.css --minify
// Corporate design system: the stock Tailwind palettes are remapped to muted, desaturated
// tones so every template picks them up without per-page edits. One accent (indigo = navy blue).
module.exports = {
  content: ['./templates/**/*.html', './crm/**/*.py'],
  theme: {
    extend: {
      fontFamily: { sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'] },
      borderRadius: { DEFAULT: '3px', md: '4px', lg: '4px', xl: '4px', '2xl': '6px' },
      boxShadow: { sm: '0 1px 1px rgba(16,24,40,.04)', DEFAULT: '0 1px 2px rgba(16,24,40,.06)' },
      colors: {
        gray:   { 50:'#f6f7f9',100:'#eceef2',200:'#dde1e7',300:'#c5cbd3',400:'#949ca8',500:'#6b7380',600:'#4f5763',700:'#3a414b',800:'#262c34',900:'#161a20',950:'#0e1115' },
        indigo: { 50:'#eef3f9',100:'#d9e4f1',200:'#b3c8e2',300:'#85a6cf',400:'#5582b8',500:'#3366a3',600:'#1f548f',700:'#184476',800:'#13365d',900:'#0f2a48',950:'#0a1c31' },
        blue:   { 50:'#f0f4f8',100:'#dde6ef',200:'#bccddf',300:'#93adc8',400:'#6a8cb0',500:'#4d7298',600:'#3d5d7e',700:'#324c67',800:'#293e54',900:'#223344',950:'#16222e' },
        violet: { 50:'#eef4f5',100:'#d6e5e8',200:'#aecbd1',300:'#7fabb4',400:'#558b96',500:'#3d717c',600:'#305c66',700:'#284b53',800:'#213c43',900:'#1b3137',950:'#122125' },
        purple: { 50:'#eef4f5',100:'#d6e5e8',200:'#aecbd1',300:'#7fabb4',400:'#558b96',500:'#3d717c',600:'#305c66',700:'#284b53',800:'#213c43',900:'#1b3137',950:'#122125' },
        green:  { 50:'#eef6f1',100:'#d5eadd',200:'#abd4bb',300:'#79b793',400:'#4c9a6e',500:'#2f7f54',600:'#246844',700:'#1e5438',800:'#19432e',900:'#153726',950:'#0d2318' },
        emerald:{ 50:'#eef6f1',100:'#d5eadd',200:'#abd4bb',300:'#79b793',400:'#4c9a6e',500:'#2f7f54',600:'#246844',700:'#1e5438',800:'#19432e',900:'#153726',950:'#0d2318' },
        yellow: { 50:'#fbf7ec',100:'#f4ead0',200:'#e8d4a1',300:'#d9b96c',400:'#c9a043',500:'#b1882e',600:'#8f6c24',700:'#6f541e',800:'#56411a',900:'#433416',950:'#2b210d' },
        amber:  { 50:'#fbf7ec',100:'#f4ead0',200:'#e8d4a1',300:'#d9b96c',400:'#c9a043',500:'#b1882e',600:'#8f6c24',700:'#6f541e',800:'#56411a',900:'#433416',950:'#2b210d' },
        orange: { 50:'#fbf1ec',100:'#f5dfd3',200:'#eabda6',300:'#db9574',400:'#c9714c',500:'#b25a36',600:'#93482b',700:'#773a25',800:'#5f3020',900:'#4c281c',950:'#2f170f' },
        red:    { 50:'#fcf2f2',100:'#f7dcdc',200:'#edb7b7',300:'#df8a8a',400:'#cc5f5f',500:'#b54343',600:'#983535',700:'#7c2c2c',800:'#642626',900:'#522121',950:'#301111' },
        rose:   { 50:'#fcf2f2',100:'#f7dcdc',200:'#edb7b7',300:'#df8a8a',400:'#cc5f5f',500:'#b54343',600:'#983535',700:'#7c2c2c',800:'#642626',900:'#522121',950:'#301111' },
        pink:   { 50:'#faf2f5',100:'#f2dde5',200:'#e4bccb',300:'#d193aa',400:'#b96d8a',500:'#9f5371',600:'#83435c',700:'#6a374b',800:'#552e3d',900:'#462733',950:'#2b151e' },
      },
    },
  },
};
