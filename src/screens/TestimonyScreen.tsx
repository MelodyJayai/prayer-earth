import Ionicons from "@expo/vector-icons/Ionicons";
import { memo, useCallback } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";
import { PageHeader } from "../components/PageHeader";
import { TestimonyCard } from "../components/TestimonyCard";
import type { Testimony } from "../domain/types";
import { useMinuteClock } from "../hooks/useMinuteClock";
import { colors } from "../theme";

export const TestimonyScreen = memo(function TestimonyScreen({
  items,
}: {
  items: Testimony[];
}) {
  const now = useMinuteClock();
  const renderItem = useCallback(
    ({ item }: { item: Testimony }) => <TestimonyCard item={item} now={now} />,
    [now],
  );
  return (
    <FlatList
      data={items}
      keyExtractor={(item) => item.id}
      renderItem={renderItem}
      contentContainerStyle={styles.content}
      initialNumToRender={4}
      windowSize={5}
      showsVerticalScrollIndicator={false}
      ListHeaderComponent={
        <>
          <PageHeader title="恩典见证" subtitle="真实故事 · 每日更新" />
          <View style={styles.intro}>
            <Text style={styles.quote}>“</Text>
            <Text style={styles.introText}>
              每一个见证都在提醒我们，{"\n"}盼望从未离开。
            </Text>
          </View>
        </>
      }
      ListEmptyComponent={
        <View style={styles.empty}>
          <Ionicons name="sparkles-outline" size={30} color={colors.green} />
          <Text style={styles.emptyTitle}>今天的见证正在整理</Text>
          <Text style={styles.emptyBody}>核实完成后会第一时间发布。</Text>
        </View>
      }
    />
  );
});

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 120 },
  intro: {
    backgroundColor: colors.mint,
    borderRadius: 19,
    padding: 20,
    marginBottom: 18,
    overflow: "hidden",
  },
  quote: {
    position: "absolute",
    fontSize: 80,
    color: "rgba(31,92,79,.10)",
    left: 12,
    top: -16,
  },
  introText: {
    fontSize: 18,
    lineHeight: 27,
    color: colors.greenDark,
    fontWeight: "600",
    textAlign: "center",
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
