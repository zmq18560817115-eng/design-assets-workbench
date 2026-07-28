import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#14151A",
        canvas: "#F7F7FC",
        panel: "#FFFFFF",
        line: "#E7E7EF",
        accent: "#5B5BF7",
        peach: "#FFF0EA",
        cyan: "#E8F8FF",
        lilac: "#F0ECFF",
      },
    },
  },
  plugins: [],
};
export default config;
