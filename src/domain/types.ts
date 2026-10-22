import type { ComponentProps } from "react";
import type { Ionicons } from "@expo/vector-icons";

export type IconName = ComponentProps<typeof Ionicons>["name"];

export const PRAYER_CATEGORIES = ["和平", "医治", "家庭", "教会"] as const;
export type PrayerCategory = (typeof PRAYER_CATEGORIES)[number];
export type PrayerFilter = "全部" | "紧急" | PrayerCategory;
export type AppTab = "首页" | "祷告" | "见证" | "我的";

export type Prayer = {
  id: string;
  title: string;
  excerpt: string;
  location: string;
  flag: string;
  category: PrayerCategory;
  prayerCount: number;
  createdAt: string;
  urgent: boolean;
  prayedByMe: boolean;
  source: "seed" | "user";
};

export type Testimony = {
  id: string;
  title: string;
  excerpt: string;
  location: string;
  flag: string;
  createdAt: string;
  imageUrl: string;
  verified: boolean;
};

export type CategoryOption = {
  label: PrayerFilter;
  icon: IconName;
};
