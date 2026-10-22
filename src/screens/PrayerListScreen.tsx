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
import { PageHeader } from "../components/PageHeader";
import { PrayerCard } from "../components/PrayerCard";
import { categoryOptions } from "../data";
import type { Prayer, PrayerFilter } from "../domain/types";
import { useMinuteClock } from "../hooks/useMinuteClock";
import { colors } from "../theme";

type Props = {
  filter: PrayerFilter;
  onFilter: (filter: PrayerFilter) => void;
  prayers: Prayer[];
  onPray: (id: string) => void;
  onOpen: (id: string) => void;
};

export const PrayerListScreen = memo(function PrayerListScreen({
  filter,
  onFilter,
  prayers,
  onPray,
  onOpen,
}: Props) {
  const now = useMinuteClock();
  const renderItem = useCallback(
    ({ item }: { item: Prayer }) => (
      <PrayerCard item={item} onPray={onPray} onOpen={onOpen} now={now} />
    ),
    [now, onOpen, onPray],
  );
  return (
    <FlatList
      data={prayers}
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
          <PageHeader title="全球祷告" subtitle="与世界一同守望" />
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.filters}
          >
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
                  <Ionicons
                    name={option.icon}
                    size={17}
                    color={active ? colors.white : colors.inkSoft}
                  />
                  <Text
                    style={[
                      styles.filterText,
                      active && styles.filterTextActive,
                    ]}
                  >
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
          <View style={styles.meta}>
            <Text style={styles.metaText}>{prayers.length} 项祷告</Text>
            <View style={styles.liveDot} />
            <Text style={styles.liveText}>每日更新</Text>
          </View>
        </>
      }
      ListEmptyComponent={
        <View style={styles.empty}>
          <Ionicons name="leaf-outline" size={30} color={colors.green} />
          <Text style={styles.emptyTitle}>这个分类暂时没有祷告</Text>
          <Text style={styles.emptyBody}>
            可以切换分类，或发布一条新的祷告。
          </Text>
        </View>
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
  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: "#3F8C6B",
    marginRight: 5,
  },
  liveText: {
    fontSize: 11,
    color: "#287052",
    fontWeight: "800",
    letterSpacing: 0.4,
  },
  empty: { alignItems: "center", paddingVertical: 56 },
  emptyTitle: {
    fontSize: 17,
    fontWeight: "700",
    color: colors.ink,
    marginTop: 14,
  },
  emptyBody: { fontSize: 13, color: colors.inkSoft, marginTop: 6 },
});
