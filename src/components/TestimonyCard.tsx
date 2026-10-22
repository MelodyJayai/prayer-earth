import Ionicons from "@expo/vector-icons/Ionicons";
import { Image } from "expo-image";
import { memo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import type { Testimony } from "../domain/types";
import { colors } from "../theme";
import { formatRelativeTime } from "../utils/formatters";

export const TestimonyCard = memo(function TestimonyCard({
  item,
  featured = false,
  now = Date.now(),
}: {
  item: Testimony;
  featured?: boolean;
  now?: number;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <View
      accessibilityLabel={`${item.title}，${item.location}`}
      style={[styles.card, featured && styles.featured]}
    >
      {imageFailed ? (
        <View style={styles.imageFallback}>
          <Ionicons name="image-outline" size={34} color="#B9D1C8" />
        </View>
      ) : (
        <Image
          source={item.imageUrl}
          style={styles.image}
          contentFit="cover"
          cachePolicy="memory-disk"
          transition={180}
          recyclingKey={item.id}
          onError={() => setImageFailed(true)}
          accessibilityLabel={`${item.title}的见证配图`}
        />
      )}
      <View style={styles.shade} />
      <View style={styles.dateBadge}>
        <Text style={styles.dateText}>
          {formatRelativeTime(item.createdAt, now)}
        </Text>
      </View>
      <View style={styles.content}>
        {item.verified && (
          <View style={styles.verified}>
            <Ionicons name="checkmark-circle" size={16} color="#CDEDE2" />
            <Text style={styles.verifiedText}>已核实见证</Text>
          </View>
        )}
        <Text style={styles.title}>{item.title}</Text>
        <Text style={styles.excerpt} numberOfLines={2}>
          {item.excerpt}
        </Text>
        <Text style={styles.location}>
          {item.flag} {item.location}
        </Text>
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  card: {
    height: 340,
    borderRadius: 22,
    overflow: "hidden",
    marginBottom: 14,
    backgroundColor: colors.greenDark,
    flexGrow: 1,
    minWidth: 300,
  },
  featured: { height: 320 },
  image: { position: "absolute", inset: 0 },
  imageFallback: {
    position: "absolute",
    inset: 0,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.green,
  },
  shade: {
    position: "absolute",
    inset: 0,
    backgroundColor: "rgba(9,31,26,.48)",
  },
  dateBadge: {
    position: "absolute",
    top: 16,
    right: 16,
    backgroundColor: "rgba(255,255,255,.94)",
    paddingHorizontal: 11,
    paddingVertical: 7,
    borderRadius: 15,
  },
  dateText: { fontSize: 12, fontWeight: "700", color: colors.ink },
  content: { position: "absolute", left: 20, right: 20, bottom: 20 },
  verified: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    marginBottom: 8,
  },
  verifiedText: { fontSize: 12, color: "#E5F5F0", fontWeight: "700" },
  title: {
    fontSize: 23,
    lineHeight: 30,
    fontWeight: "700",
    color: colors.white,
  },
  excerpt: { fontSize: 14, lineHeight: 21, color: "#F0F6F4", marginTop: 8 },
  location: { fontSize: 12, color: "#E1EDE9", marginTop: 11 },
});
