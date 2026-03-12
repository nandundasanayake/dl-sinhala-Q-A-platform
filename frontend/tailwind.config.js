/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dopamine: {
          dark: '#1b1035',
          light: '#f2e8fa',
          accent: '#8b5cf6',
        }
      }
    },
  },
  plugins: [],
}