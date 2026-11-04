import Ionicons from "@expo/vector-icons/Ionicons";
import { memo, useCallback } from "react";
import {
  FlatList,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { DemoDataNotice } from "../components/DemoDataNotice";
import { PageHeader } from "../components/PageHeader";
import { PrayerCard } from "../components/PrayerCard";
import { categoryOptions } from "../data";
import type { Prayer, PrayerFilter } from "../domain/types";
import { useMinuteClock } from "../hooks/useMinuteClock";
import type { PrayerFeedStatus } from "../state/prayerReducer";
import { colors } from "../theme";

type Props = {
  filter: PrayerFilter;
  onFilter: (filter: PrayerFilter) => void;
  prayers: Prayer[];
  feedStatus?: PrayerFeedStatus;
  onPray: (id: string) => void;
  onOpen: (id: string) => void;
};

export const PrayerListScreen = memo(function PrayerListScreen({
  filter,
  onFilter,
  prayers,
  feedStatus = "ready",
  onPray,
  onOpen,
}: Props) {
  const now = useMinuteClock();
  const news = prayers.filter((item) => item.source === "news");
  const mine = prayers.filter((item) => {
    if (item.source !== "user") return false;
    return filter === "全部" || (filter === "紧急" ? item.urgent : item.category === filter);
  });
  const showingSeeds = prayers.some((item) => item.source === "seed");
  const emptyCopy = feedStatus === "loading"
    ? "正在读取需要代祷的动态"
    : feedStatus === "error"
      ? "暂时无法读取需要代祷的动态"
      : "暂无需要代祷的动态";
  const renderItem = useCallback(
    ({ item }: { item: Prayer }) => (
      <PrayerCard item={item} onPray={onPray} onOpen={onOpen} now={now} />
    ),
    [now, onOpen, onPray],
  );
  return (
    <FlatList
      data={news}
      keyExtractor={(item) => item.id}
      renderItem={renderItem}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
      initialNumToRender={6}
      maxToRenderPerBatch={6}
      updateCellsBatchingPeriod={40}
      windowSize={7}
      removeClippedSubviews={Platform.OS === "android"}
      keyboardDismissMode="on-drag"
      ListHeaderComponent={
        <>
          <PageHeader title="全球祷告" subtitle="需要代祷的宗教动态" />
          {showingSeeds ? <DemoDataNotice /> : null}
          <Text style={styles.intro}>
            这些条目来自已公开的宗教动态。已核实且涉及迫害的会自动出现；未核实的要同工确认后才列出，并标为待核实。人数不再汇总。「我来祷告」只记在这台设备上。
          </Text>
          <View style={styles.meta}>
            <Text style={styles.metaText}>
              {news.length > 0 ? `${news.length} 条需要代祷的动态` : emptyCopy}
            </Text>
          </View>
        </>
      }
      ListEmptyComponent={
        news.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="leaf-outline" size={30} color={colors.green} />
            <Text style={styles.emptyTitle}>{emptyCopy}</Text>
            <Text style={styles.emptyBody}>
              {feedStatus === "ready"
                ? "同工尚未标出需要代祷的动态。你仍可以发布一条只保存在这台设备上的祷告。"
                : "请稍后再打开这一页。你仍可以发布一条只保存在这台设备上的祷告。"}
            </Text>
          </View>
        ) : null
      }
      ListFooterComponent={
        prayers.some((item) => item.source === "user") ? (
          <View>
            <Text style={styles.mineTitle}>保存在这台设备上的祷告</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
              {categoryOptions.map((option) => {
                const active = option.label === filter;
                return (
                  <Pressable
                    accessibilityRole="radio"
                    accessibilityState={{ checked: active }}
                    key={option.label}
                    onPress={() => onFilter(option.label)}
                    style={[styles.filter, active && styles.filterActive]}
                  >
                    <Ionicons name={option.icon} size={17} color={active ? colors.white : colors.inkSoft} />
                    <Text style={[styles.filterText, active && styles.filterTextActive]}>{option.label}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            {mine.length === 0 ? <Text style={styles.emptyBody}>这个分类下还没有本机祷告。</Text> : null}
            {mine.map((item) => (
              <PrayerCard key={item.id} item={item} onPray={onPray} onOpen={onOpen} now={now} />
            ))}
          </View>
        ) : null
      }
    />
  );
});

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 120 },
  filters: { gap: 9, paddingRight: 20, marginBottom: 20 },
  filter: {
    minHeight: 44,
    paddingHorizontal: 14,
    borderRadius: 22,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  filterActive: { backgroundColor: colors.green, borderColor: colors.green },
  filterText: { fontSize: 13, color: colors.inkSoft, fontWeight: "600" },
  filterTextActive: { color: colors.white },
  meta: { flexDirection: "row", alignItems: "center", marginBottom: 12 },
  metaText: { fontSize: 12, color: colors.inkSoft, flex: 1 },
  intro: { fontSize: 13, lineHeight: 20, color: colors.inkSoft, marginBottom: 14 },
  mineTitle: { fontSize: 16, fontWeight: "700", color: colors.ink, marginTop: 8, marginBottom: 12 },
  empty: { alignItems: "center", paddingVertical: 56 },
  emptyTitle: {
    fontSize: 17,
    fontWeight: "700",
    color: colors.ink,
    marginTop: 14,
  },
  emptyBody: { fontSize: 13, color: colors.inkSoft, marginTop: 6 },
});
