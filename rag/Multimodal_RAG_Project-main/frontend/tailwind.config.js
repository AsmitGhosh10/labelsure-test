/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{js,ts,tsx,jsx}",
  ],
  theme: {
    extend: {
      background: "#09090B",
      foreground: "#FAFAFA",
      card: "#111113",
      border: "#27272A",
      muted: "#71717A",
      primary: "#7C3AED",
    },
    backdropBlur: {
      xs: "2px",
    },
  },
  plugins: [],
}

