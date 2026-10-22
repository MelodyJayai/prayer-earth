import type { CategoryOption, Prayer, Testimony } from "./domain/types";

const minutesAgo = (minutes: number) =>
  new Date(Date.now() - minutes * 60_000).toISOString();

export const seedPrayers: Prayer[] = [
  {
    id: "seed-sudan-peace",
    title: "为苏丹流离失所的家庭祷告",
    excerpt: "愿和平临到这片土地，为正在寻找安全住所的家庭开道路。",
    location: "喀土穆，苏丹",
    flag: "🇸🇩",
    category: "和平",
    prayerCount: 12_847,
    createdAt: minutesAgo(12),
    urgent: true,
    prayedByMe: false,
    source: "seed",
  },
  {
    id: "seed-taipei-healing",
    title: "为小安的康复献上祷告",
    excerpt: "她正在接受心脏手术，求神赐医生智慧，也安慰等待中的家人。",
    location: "台北，中国",
    flag: "🇨🇳",
    category: "医治",
    prayerCount: 3_604,
    createdAt: minutesAgo(36),
    urgent: false,
    prayedByMe: false,
    source: "seed",
  },
  {
    id: "seed-ishikawa-family",
    title: "为震后重建的社区守望",
    excerpt: "愿每个家庭得着供应，让孩子们可以重新回到安全的校园。",
    location: "石川县，日本",
    flag: "🇯🇵",
    category: "家庭",
    prayerCount: 8_271,
    createdAt: minutesAgo(60),
    urgent: false,
    prayedByMe: false,
    source: "seed",
  },
  {
    id: "seed-nairobi-church",
    title: "为青年团契的新开始感恩",
    excerpt: "求神带领年轻人在爱中彼此建造，成为城市里的光。",
    location: "内罗毕，肯尼亚",
    flag: "🇰🇪",
    category: "教会",
    prayerCount: 1_942,
    createdAt: minutesAgo(120),
    urgent: false,
    prayedByMe: false,
    source: "seed",
  },
];

export const testimonies: Testimony[] = [
  {
    id: "testimony-brazil-reunion",
    title: "失联七天后，一家人在爱中重聚",
    excerpt: "来自不同城市的志愿者接力寻找，终于在暴雨后的第七天带来了好消息。",
    location: "南里奥格兰德，巴西",
    flag: "🇧🇷",
    createdAt: minutesAgo(180),
    imageUrl:
      "https://images.unsplash.com/photo-1529156069898-49953e39b3ac?auto=format&fit=crop&w=1000&q=80",
    verified: true,
  },
  {
    id: "testimony-philippines-recovery",
    title: "医生说不可能，她却重新站了起来",
    excerpt: "六个月的祷告、陪伴与康复训练，让这个家庭再次看见盼望。",
    location: "马尼拉，菲律宾",
    flag: "🇵🇭",
    createdAt: minutesAgo(1_440),
    imageUrl:
      "https://images.unsplash.com/photo-1478476868527-002ae3f3e159?auto=format&fit=crop&w=1000&q=80",
    verified: true,
  },
];

export const categoryOptions: CategoryOption[] = [
  { label: "全部", icon: "earth-outline" },
  { label: "紧急", icon: "alert-circle-outline" },
  { label: "和平", icon: "leaf-outline" },
  { label: "医治", icon: "heart-outline" },
  { label: "家庭", icon: "home-outline" },
  { label: "教会", icon: "people-outline" },
];
