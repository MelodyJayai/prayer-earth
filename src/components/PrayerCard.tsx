import Ionicons from "@expo/vector-icons/Ionicons";
import { memo, useCallback } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { Prayer } from "../domain/types";
import { SourceLink } from "./NewsItemCard";
import { colors } from "../theme";
import { formatRelativeTime } from "../utils/formatters";

type Props = {
  item: Prayer;
  onPray: (id: string) => void;
  onOpen: (id: string) => void;
  compact?: boolean;
  now?: number;
};

export const PrayerCard = memo(function PrayerCard({
  item,
  onPray,
  onOpen,
  compact = false,
  now = Date.now(),
}: Props) {
  const open = useCallback(() => onOpen(item.id), [item.id, onOpen]);
  const pray = useCallback(() => onPray(item.id), [item.id, onPray]);
  const unverified = item.source === "news" && item.verified === false;
  const when = item.source === "news" ? item.createdAt.slice(0, 10) : formatRelativeTime(item.createdAt, now);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.title}，${item.location}`}
      onPress={open}
      style={({ pressed }) => [
        styles.card,
        compact && styles.compact,
        pressed && styles.cardPressed,
      ]}
    >
      <View style={styles.top}>
        <View style={[styles.badge, item.urgent && styles.urgentBadge]}>
          <Text style={[styles.badgeText, item.urgent && styles.urgentText]}>
            {item.urgent ? "紧急 · " : ""}
            {item.source === "news" ? "代祷" : item.category}
          </Text>
        </View>
        {unverified ? (
          <View style={styles.unverified}>
            <Text style={styles.unverifiedText}>待核实</Text>
          </View>
        ) : null}
        <Text style={styles.time}>{when}</Text>
      </View>
      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.excerpt} numberOfLines={2}>
        {item.excerpt}
      </Text>
      <View style={styles.location}>
        {item.flag ? <Text style={styles.flag}>{item.flag}</Text> : null}
        <Text style={styles.locationText}>{item.location}</Text>
      </View>
      {item.source === "news" && item.sourceUrl && item.sourceName ? (
        <View style={styles.sourceRow}>
          <Text style={styles.locationText}>来源：</Text>
          <SourceLink href={item.sourceUrl}>{item.sourceName}</SourceLink>
        </View>
      ) : null}
      <View style={styles.divider} />
      <View style={styles.bottom}>
        <View style={styles.people}>
          <Text style={styles.peopleText}>
            {item.prayedByMe
              ? "你已为此祷告"
              : item.source === "user"
                ? "只保存在这台设备"
                : "祷告记录只留在这台设备"}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={item.prayedByMe ? "撤销祷告记录" : "我来祷告"}
          accessibilityState={{ selected: item.prayedByMe }}
          hitSlop={6}
          onPress={(event) => {
            event.stopPropagation();
            pray();
          }}
          style={({ pressed }) => [
            styles.prayButton,
            item.prayedByMe && styles.prayButtonDone,
            pressed && styles.buttonPressed,
          ]}
        >
          <Ionicons
            name={item.prayedByMe ? "checkmark" : "heart-outline"}
            size={18}
            color={item.prayedByMe ? colors.white : colors.green}
          />
          <Text
            style={[styles.prayText, item.prayedByMe && styles.prayTextDone]}
          >
            {item.prayedByMe ? "已祷告" : "我来祷告"}
          </Text>
        </Pressable>
      </View>
    </Pressable>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.white,
    borderRadius: 19,
    padding: 18,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: "#E1E5E0",
  },
  compact: { width: "48.8%", flexGrow: 1 },
  cardPressed: { opacity: 0.88 },
  top: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  badge: {
    backgroundColor: colors.mint,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 10,
  },
  urgentBadge: { backgroundColor: "#FBE7E2" },
  badgeText: { fontSize: 12, fontWeight: "700", color: colors.green },
  urgentText: { color: "#A84535" },
  unverified: { backgroundColor: "#FFF4DA", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10 },
  unverifiedText: { fontSize: 12, fontWeight: "700", color: "#856417" },
  time: { fontSize: 12, color: colors.inkSoft, marginLeft: "auto" },
  sourceRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", marginTop: 8 },
  title: {
    fontSize: 17,
    fontWeight: "700",
    color: colors.ink,
    lineHeight: 24,
    marginTop: 13,
  },
  excerpt: {
    fontSize: 14,
    color: colors.inkSoft,
    lineHeight: 21,
    marginTop: 7,
  },
  location: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 12,
  },
  flag: { fontSize: 15 },
  locationText: { fontSize: 12, color: colors.inkSoft },
  divider: { height: 1, backgroundColor: colors.line, marginVertical: 14 },
  bottom: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  people: { flexDirection: "row", alignItems: "center", flexShrink: 1 },
  peopleText: { fontSize: 12, color: colors.inkSoft },
  prayButton: {
    minHeight: 44,
    paddingHorizontal: 13,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "#9ABCAF",
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },
  prayButtonDone: { backgroundColor: colors.green, borderColor: colors.green },
  prayText: { fontSize: 12, fontWeight: "700", color: colors.green },
  prayTextDone: { color: colors.white },
  buttonPressed: { opacity: 0.72 },
});
