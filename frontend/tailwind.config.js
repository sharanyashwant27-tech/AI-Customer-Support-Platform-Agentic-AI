/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef7f4",
          100: "#d5ebe3",
          500: "#1f6f5b",
          700: "#145043",
          900: "#0b2e26",
        },
        ink: "#12202a",
        mist: "#f3f6f8",
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"Source Sans 3"', "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
