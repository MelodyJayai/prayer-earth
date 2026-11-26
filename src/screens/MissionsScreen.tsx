import Ionicons from "@expo/vector-icons/Ionicons";
import { memo, useCallback, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { MissionCard } from "../components/MissionCard";
import { PageHeader } from "../components/PageHeader";
import { SectionSwitch, type BoardSection } from "../components/SectionSwitch";
import { MISSION_KINDS, type MissionItem, type MissionKind } from "../services/missionsFeed";
import { colors } from "../theme";

export type MissionsStatus = "loading" | "ready" | "error";

export const MissionsScreen = memo(function MissionsScreen({
  items,
  status,
  onRefresh,
  onSwitchSection,
}: {
  items: MissionItem[];
  status: MissionsStatus;
  onRefresh: () => void;
  onSwitchSection: (section: BoardSection) => void;
}) {
  const [kind, setKind] = useState<MissionKind | "全部">("全部");
  const filtered = useMemo(
    () => items.filter((item) => kind === "全部" || item.kind === kind),
    [items, kind],
  );
  const renderItem = useCallback(({ item }: { item: MissionItem }) => <MissionCard item={item} />, []);
  const emptyCopy = status === "loading"
    ? "正在读取宣教动态"
    : status === "error"
      ? "暂时无法读取宣教动态"
      : "这个分类下暂时没有条目";
  return (
    <FlatList
      data={filtered}
      keyExtractor={(item) => item.id}
      renderItem={renderItem}
      onRefresh={onRefresh}
      refreshing={status === "loading" && items.length > 0}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
      initialNumToRender={6}
      windowSize={7}
      ListHeaderComponent={
        <>
          <PageHeader title="宣教动态·报告·会议" subtitle="全球教会宣教" />
          <SectionSwitch active="missions" onSelect={onSwitchSection} />
          <Text style={styles.intro}>
            这里收录宗教动态筛查中发现的大型区域性宣教会议、宣教进展和研究报告，只显示标题、短摘要和来源链接，不转载全文。尚未双源核实的会标为待核实。
          </Text>
          <View style={styles.tabs}>
            {(["全部", ...MISSION_KINDS] as const).map((value) => (
              <Pressable
                key={value}
                accessibilityRole="tab"
                accessibilityState={{ selected: kind === value }}
                onPress={() => setKind(value)}
                style={[styles.tab, kind === value && styles.tabActive]}
              >
                <Text style={[styles.tabText, kind === value && styles.tabTextActive]}>{value}</Text>
              </Pressable>
            ))}
          </View>
          <View style={styles.meta}>
            <Text style={styles.metaText}>
              {filtered.length > 0 ? `共 ${filtered.length} 条 · 按日期从新到旧` : emptyCopy}
            </Text>
            <Pressable accessibilityRole="button" onPress={onRefresh} disabled={status === "loading"} hitSlop={8}>
              <Text style={styles.refresh}>{status === "loading" ? "更新中…" : "刷新"}</Text>
            </Pressable>
          </View>
        </>
      }
      ListEmptyComponent={
        <View style={styles.empty}>
          <Ionicons name="globe-outline" size={30} color={colors.green} />
          <Text style={styles.emptyTitle}>{emptyCopy}</Text>
        </View>
      }
    />
  );
});

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 120 },
  intro: { fontSize: 13, lineHeight: 20, color: colors.inkSoft, marginBottom: 14 },
  tabs: { flexDirection: "row", gap: 8, marginBottom: 12 },
  tab: { paddingVertical: 8, paddingHorizontal: 16, borderRadius: 18, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white },
  tabActive: { backgroundColor: colors.green, borderColor: colors.green },
  tabText: { fontSize: 13, color: colors.inkSoft, fontWeight: "600" },
  tabTextActive: { color: colors.white },
  meta: { flexDirection: "row", alignItems: "center", marginBottom: 12 },
  metaText: { fontSize: 12, color: colors.inkSoft, flex: 1 },
  refresh: { fontSize: 12, color: colors.green, fontWeight: "700" },
  empty: { alignItems: "center", paddingVertical: 56 },
  emptyTitle: { fontSize: 15, fontWeight: "700", color: colors.ink, marginTop: 14 },
});
