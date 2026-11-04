import Ionicons from "@expo/vector-icons/Ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { memo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { DemoDataNotice } from "../components/DemoDataNotice";
import { PageHeader } from "../components/PageHeader";
import { PrayerCard } from "../components/PrayerCard";
import { importedContentItems } from "../contentData";
import { isTextNewsItem, type FeedItem } from "../services/contentFeed";
import type { AppTab, Prayer } from "../domain/types";
import type { PrayerFeedStatus } from "../state/prayerReducer";
import { useMinuteClock } from "../hooks/useMinuteClock";
import { colors } from "../theme";
import { formatToday } from "../utils/formatters";

type Props = {
  wide: boolean;
  prayers: Prayer[];
  feedStatus?: PrayerFeedStatus;
  contentItems?: FeedItem[];
  onPray: (id: string) => void;
  onOpen: (id: string) => void;
  onTab: (tab: AppTab) => void;
};

export const HomeScreen = memo(function HomeScreen({
  wide,
  prayers,
  feedStatus = "ready",
  contentItems = importedContentItems,
  onPray,
  onOpen,
  onTab,
}: Props) {
  const now = useMinuteClock();
  const morningCount = contentItems.filter((item) => item.channel === "晨修").length;
  const missionCount = contentItems.filter((item) => item.channel === "宣教动态与见证").length;
  const newsCount = contentItems.filter((item) => isTextNewsItem(item)).length;
  const prayerNews = prayers.filter((item) => item.source === "news").slice(0, 3);
  const mine = prayers.filter((item) => item.source === "user").slice(0, 2);
  const showingSeeds = prayers.some((item) => item.source === "seed");
  const prayerEmpty = feedStatus === "loading"
    ? "正在读取需要代祷的动态"
    : feedStatus === "error"
      ? "暂时无法读取需要代祷的动态"
      : "暂无需要代祷的动态";
  return (
    <ScrollView
      showsVerticalScrollIndicator={false}
      contentContainerStyle={styles.content}
      keyboardDismissMode="on-drag"
    >
      <PageHeader
        title="愿平安临到世界"
        subtitle={formatToday(new Date(now))}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="进入全球祷告"
        onPress={() => onTab("祷告")}
        style={({ pressed }) => [pressed && styles.pressed]}
      >
        <LinearGradient
          colors={[colors.green, colors.greenDark]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.hero}
        >
          <View style={styles.orbOne} />
          <View style={styles.orbTwo} />
          <Text style={styles.kicker}>全球祷告</Text>
          <Text style={styles.heroTitle}>进入祷告列表</Text>
          <Text style={styles.heroBody}>
            查看同工标出的、需要代祷的宗教动态。来源可以打开核对。「我来祷告」只记在这台设备上。
          </Text>
          <View style={styles.heroButton}>
            <Ionicons name="earth" size={18} color={colors.greenDark} />
            <Text style={styles.heroButtonText}>进入全球祷告</Text>
            <Ionicons name="arrow-forward" size={16} color={colors.greenDark} />
          </View>
        </LinearGradient>
      </Pressable>
      <SectionTitle
        title="需要代祷的动态"
        action="查看全部"
        onPress={() => onTab("祷告")}
      />
      {showingSeeds ? <DemoDataNotice /> : null}
      {prayerNews.length === 0 ? <Text style={styles.emptyCopy}>{prayerEmpty}</Text> : null}
      <View style={wide ? styles.columns : undefined}>
        {prayerNews.map((item) => (
          <PrayerCard
            key={item.id}
            item={item}
            onPray={onPray}
            onOpen={onOpen}
            compact={wide}
            now={now}
          />
        ))}
      </View>
      {mine.length > 0 ? (
        <>
          <SectionTitle title="保存在这台设备上的祷告" action="查看全部" onPress={() => onTab("祷告")} />
          <View style={wide ? styles.columns : undefined}>
            {mine.map((item) => (
              <PrayerCard key={item.id} item={item} onPray={onPray} onOpen={onOpen} compact={wide} now={now} />
            ))}
          </View>
        </>
      ) : null}
      <SectionTitle
        title="同工内容"
        action="打开内容库"
        onPress={() => onTab("见证")}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="打开晨修与宣教动态内容库"
        onPress={() => onTab("见证")}
        style={({ pressed }) => [styles.contentTeaser, pressed && styles.pressed]}
      >
        <View style={styles.contentTeaserIcon}>
          <Ionicons name="book-outline" size={24} color={colors.green} />
        </View>
        <View style={styles.contentTeaserCopy}>
          <Text style={styles.contentTeaserTitle}>晨修 · 宣教动态与见证</Text>
          <Text style={styles.contentTeaserBody}>
            共 {morningCount} 条晨修、{missionCount} 条宣教动态图片{newsCount > 0 ? `，${newsCount} 条宗教动态` : ""}，按日期持续更新。
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.muted} />
      </Pressable>
      <View style={styles.verse}>
        <Ionicons name="book-outline" size={21} color="#8D641F" />
        <View style={styles.verseCopy}>
          <Text style={styles.verseLabel}>每日经文</Text>
          <Text style={styles.verseText}>“你们要恒切祷告，在此警醒感恩。”</Text>
          <Text style={styles.verseRef}>歌罗西书 4:2</Text>
        </View>
      </View>
    </ScrollView>
  );
});

function SectionTitle({
  title,
  action,
  onPress,
}: {
  title: string;
  action: string;
  onPress: () => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        {title}
      </Text>
      <Pressable accessibilityRole="button" hitSlop={8} onPress={onPress}>
        <Text style={styles.sectionAction}>{action} ›</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 120 },
  hero: {
    padding: 24,
    borderRadius: 24,
    minHeight: 244,
    overflow: "hidden",
    marginBottom: 8,
  },
  orbOne: {
    position: "absolute",
    width: 180,
    height: 180,
    borderRadius: 90,
    backgroundColor: "rgba(255,255,255,.055)",
    right: -34,
    top: -44,
  },
  orbTwo: {
    position: "absolute",
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,.08)",
    right: 35,
    bottom: -55,
  },
  kicker: {
    color: "#D6E9E2",
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 1.1,
    marginBottom: 14,
  },
  heroTitle: {
    fontSize: 28,
    lineHeight: 37,
    fontWeight: "700",
    color: colors.white,
    letterSpacing: -0.4,
  },
  heroBody: {
    fontSize: 14,
    lineHeight: 22,
    color: "#D7E6E1",
    marginTop: 12,
    maxWidth: 400,
  },
  heroButton: {
    minHeight: 52,
    marginTop: 18,
    paddingHorizontal: 18,
    borderRadius: 26,
    backgroundColor: colors.white,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  heroButtonText: { color: colors.greenDark, fontSize: 16, fontWeight: "800" },
  emptyCopy: { fontSize: 14, lineHeight: 22, color: colors.inkSoft, marginBottom: 8 },
  section: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 28,
    marginBottom: 14,
  },
  sectionTitle: { fontSize: 19, fontWeight: "700", color: colors.ink },
  sectionAction: {
    fontSize: 13,
    color: colors.green,
    fontWeight: "700",
    paddingVertical: 6,
  },
  columns: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  contentTeaser: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 16,
    borderRadius: 18,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
  },
  contentTeaserIcon: {
    width: 48,
    height: 48,
    borderRadius: 15,
    backgroundColor: colors.mint,
    alignItems: "center",
    justifyContent: "center",
  },
  contentTeaserCopy: { flex: 1 },
  contentTeaserTitle: { fontSize: 15, fontWeight: "700", color: colors.ink },
  contentTeaserBody: { fontSize: 12, lineHeight: 18, color: colors.inkSoft, marginTop: 4 },
  verse: {
    marginTop: 22,
    padding: 19,
    backgroundColor: "#F1EBDD",
    borderRadius: 18,
    flexDirection: "row",
    gap: 14,
  },
  verseCopy: { flex: 1 },
  verseLabel: {
    fontSize: 12,
    color: "#76541C",
    fontWeight: "800",
    letterSpacing: 0.6,
  },
  verseText: {
    fontSize: 15,
    color: colors.ink,
    lineHeight: 23,
    marginTop: 5,
    fontWeight: "600",
  },
  verseRef: { fontSize: 12, color: colors.inkSoft, marginTop: 4 },
  pressed: { opacity: 0.7 },
});
