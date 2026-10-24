/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        dark: {
          950: "#0b0d13",
          900: "#11141d",
          850: "#151924",
          800: "#1c2130",
          700: "#282f44",
          600: "#3b4461",
          500: "#505c80",
          400: "#7b87ab",
          300: "#a9b4d4",
          200: "#d3dbf0",
          100: "#edf1fa",
        },
        godot: {
          blue: "#478cbf",
          dark: "#202531",
          light: "#78b4e3",
          accent: "#2ecc71",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};
