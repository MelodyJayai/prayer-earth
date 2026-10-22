import Ionicons from "@expo/vector-icons/Ionicons";
import { Image } from "expo-image";
import { memo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { ImportedContentItem } from "../contentData";
import { colors } from "../theme";

export const ContentItemCard = memo(function ContentItemCard({
  item,
  onPress,
}: {
  item: ImportedContentItem;
  onPress: () => void;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.channel}，${item.date}，打开完整图片`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.preview}>
        {failed ? (
          <View style={styles.fallback}>
            <Ionicons name="image-outline" size={28} color={colors.muted} />
            <Text style={styles.fallbackText}>图片预览不可用</Text>
          </View>
        ) : (
          <Image
            source={item.image}
            style={styles.image}
            contentFit="contain"
            cachePolicy="memory-disk"
            onError={() => setFailed(true)}
            accessibilityLabel={`${item.date} ${item.channel}图片`}
          />
        )}
      </View>
      <View style={styles.meta}>
        <View style={styles.metaTop}>
          <View style={[styles.badge, item.channel === "晨修" ? styles.morning : styles.mission]}>
            <Text style={styles.badgeText}>{item.channel}</Text>
          </View>
          <Text style={styles.date}>{item.date}</Text>
        </View>
        <Text style={styles.title}>{item.title}</Text>
        <Text style={styles.excerpt}>{item.excerpt}</Text>
        <View style={styles.openHint}>
          <Ionicons name="expand-outline" size={16} color={colors.green} />
          <Text style={styles.openHintText}>打开完整内容</Text>
        </View>
      </View>
    </Pressable>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.white,
    borderRadius: 18,
    overflow: "hidden",
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.line,
  },
  preview: {
    height: 250,
    backgroundColor: "#EEF3F0",
    alignItems: "center",
    justifyContent: "center",
  },
  image: { width: "100%", height: "100%" },
  fallback: { alignItems: "center", gap: 8 },
  fallbackText: { color: colors.muted, fontSize: 12 },
  meta: { padding: 15 },
  metaTop: { flexDirection: "row", alignItems: "center", gap: 9 },
  badge: { borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5 },
  morning: { backgroundColor: "#F1EBDD" },
  mission: { backgroundColor: colors.mint },
  badgeText: { color: colors.greenDark, fontSize: 12, fontWeight: "700" },
  date: { color: colors.inkSoft, fontSize: 12 },
  title: { color: colors.ink, fontSize: 17, fontWeight: "700", marginTop: 11 },
  excerpt: { color: colors.inkSoft, fontSize: 13, lineHeight: 20, marginTop: 5 },
  openHint: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 12 },
  openHintText: { color: colors.green, fontSize: 12, fontWeight: "700" },
  pressed: { opacity: 0.76 },
});
