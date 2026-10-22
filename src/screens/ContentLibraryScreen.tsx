import Ionicons from "@expo/vector-icons/Ionicons";
import { memo, useCallback, useMemo, useState } from "react";
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { ContentItemCard } from "../components/ContentItemCard";
import type { ContentChannel, ImportedContentItem } from "../contentData";
import { colors } from "../theme";

const channels: (ContentChannel | "全部")[] = ["全部", "晨修", "宣教动态与见证"];

export const ContentLibraryScreen = memo(function ContentLibraryScreen({
  items,
  onOpen,
  onRefresh,
  refreshing = false,
  updateError,
}: {
  items: ImportedContentItem[];
  onOpen: (id: string) => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  updateError?: string | null;
}) {
  const [channel, setChannel] = useState<ContentChannel | "全部">("晨修");
  const [query, setQuery] = useState("");
  const [month, setMonth] = useState("全部月份");
  const months = useMemo(
    () => ["全部月份", ...new Set(items.map((item) => item.date.slice(0, 7)).sort().reverse())],
    [items],
  );
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items
      .filter((item) => channel === "全部" || item.channel === channel)
      .filter((item) => month === "全部月份" || item.date.startsWith(month))
      .filter((item) => !normalized || `${item.title} ${item.excerpt} ${item.searchText}`.toLowerCase().includes(normalized))
      .sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id));
  }, [channel, items, month, query]);
  const renderItem = useCallback(
    ({ item }: { item: ImportedContentItem }) => (
      <ContentItemCard item={item} onPress={() => onOpen(item.id)} />
    ),
    [onOpen],
  );
  return (
    <FlatList
      data={filtered}
      keyExtractor={(item) => item.id}
      renderItem={renderItem}
      onRefresh={onRefresh}
      refreshing={refreshing}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
      initialNumToRender={4}
      windowSize={5}
      ListHeaderComponent={
        <View>
          <Text style={styles.eyebrow}>微信群内容试用版</Text>
          <Text style={styles.title}>晨修与宣教动态</Text>
          <Text style={styles.subtitle}>按栏目、月份浏览已导入的完整清晰图片，点击卡片阅读原图。</Text>
          <View style={styles.tabs}>
            {channels.map((item) => (
              <Pressable
                key={item}
                accessibilityRole="tab"
                accessibilityState={{ selected: channel === item }}
                onPress={() => setChannel(item)}
                style={[styles.tab, channel === item && styles.activeTab]}
              >
                <Text style={[styles.tabText, channel === item && styles.activeTabText]}>{item}</Text>
              </Pressable>
            ))}
          </View>
          <View style={styles.searchBox}>
            <Ionicons name="search-outline" size={18} color={colors.muted} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="搜索日期或内容"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              accessibilityLabel="搜索内容"
            />
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.months}>
            {months.map((item) => (
              <Pressable key={item} onPress={() => setMonth(item)} style={[styles.month, month === item && styles.activeMonth]}>
                <Text style={[styles.monthText, month === item && styles.activeMonthText]}>{item}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <View style={styles.updateRow}>
            <Text style={styles.count}>共 {filtered.length} 条 · 按日期从新到旧排列</Text>
            {onRefresh && <Pressable accessibilityRole="button" onPress={onRefresh} disabled={refreshing} hitSlop={8}><Text style={styles.refresh}>{refreshing ? "更新中…" : "刷新内容"}</Text></Pressable>}
          </View>
          {updateError && <Text style={styles.updateError}>{updateError}</Text>}
        </View>
      }
      ListEmptyComponent={<Text style={styles.empty}>当前筛选条件下没有内容。</Text>}
    />
  );
});

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 120 },
  eyebrow: { color: colors.inkSoft, fontSize: 13, marginBottom: 5 },
  title: { color: colors.ink, fontSize: 29, fontWeight: "700", letterSpacing: -0.7 },
  subtitle: { color: colors.inkSoft, fontSize: 13, lineHeight: 20, marginTop: 9, marginBottom: 16 },
  tabs: { flexDirection: "row", backgroundColor: colors.mint, borderRadius: 14, padding: 4, marginBottom: 12 },
  tab: { flex: 1, alignItems: "center", paddingVertical: 10, borderRadius: 11 },
  activeTab: { backgroundColor: colors.white },
  tabText: { color: colors.inkSoft, fontSize: 13, fontWeight: "600", textAlign: "center" },
  activeTabText: { color: colors.greenDark, fontWeight: "800" },
  searchBox: { minHeight: 45, flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 13, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.line, borderRadius: 13 },
  searchInput: { flex: 1, color: colors.ink, fontSize: 14 },
  months: { gap: 8, paddingVertical: 13 },
  month: { borderRadius: 14, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.line },
  activeMonth: { backgroundColor: colors.green, borderColor: colors.green },
  monthText: { color: colors.inkSoft, fontSize: 12 },
  activeMonthText: { color: colors.white, fontWeight: "700" },
  count: { color: colors.muted, fontSize: 12, marginBottom: 12 },
  updateRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", gap: 8 },
  refresh: { color: colors.green, fontSize: 12, fontWeight: "700", paddingVertical: 5 },
  updateError: { color: colors.inkSoft, fontSize: 12, marginBottom: 12 },
  empty: { color: colors.inkSoft, textAlign: "center", paddingVertical: 60 },
});
