import { memo } from "react";
import { StyleSheet, Text, View } from "react-native";
import type { MissionItem } from "../services/missionsFeed";
import { colors } from "../theme";
import { SourceLink } from "./NewsItemCard";

export const MissionCard = memo(function MissionCard({ item }: { item: MissionItem }) {
  return (
    <View style={styles.card}>
      <View style={styles.metaTop}>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{item.kind}</Text>
        </View>
        {item.verified ? null : (
          <View style={styles.unverified}>
            <Text style={styles.unverifiedText}>待核实</Text>
          </View>
        )}
        <Text style={styles.date}>{item.date}</Text>
      </View>
      <Text style={styles.title}>{item.title}</Text>
      {item.eventDate ? <Text style={styles.eventDate}>活动日期：{item.eventDate}</Text> : null}
      <Text style={styles.summary}>{item.summary}</Text>
      <Text style={styles.region}>{item.region}</Text>
      <View style={styles.sourceRow}>
        <Text style={styles.sourceLabel}>来源：</Text>
        <SourceLink href={item.sourceUrl}>{item.sourceName}</SourceLink>
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  card: { backgroundColor: colors.white, borderRadius: 18, marginBottom: 14, borderWidth: 1, borderColor: colors.line, padding: 15 },
  metaTop: { flexDirection: "row", alignItems: "center", gap: 9, flexWrap: "wrap" },
  badge: { borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: colors.mint },
  badgeText: { color: colors.greenDark, fontSize: 12, fontWeight: "700" },
  unverified: { borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: "#FFF4DA" },
  unverifiedText: { color: "#856417", fontSize: 12, fontWeight: "700" },
  date: { color: colors.inkSoft, fontSize: 12 },
  title: { color: colors.ink, fontSize: 17, fontWeight: "700", marginTop: 11 },
  eventDate: { color: colors.greenDark, fontSize: 13, fontWeight: "600", marginTop: 5 },
  summary: { color: colors.inkSoft, fontSize: 13, lineHeight: 20, marginTop: 5 },
  region: { color: colors.muted, fontSize: 12, marginTop: 8 },
  sourceRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", marginTop: 10 },
  sourceLabel: { color: colors.inkSoft, fontSize: 13 },
});
