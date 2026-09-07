import { create } from "zustand";

type Theme = "dark" | "light";

interface ThemeStore {
      theme : Theme;
      toggleTheme : () => void;
}

export const ThemeStore = create<ThemeStore>((set) => ({
      theme : "dark",

      toggleTheme: () => 
            set((state) => ({
                  theme : state.theme === "dark" ? "light" : "dark",
            })),
}));