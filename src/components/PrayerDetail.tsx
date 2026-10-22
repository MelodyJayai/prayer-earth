import Ionicons from "@expo/vector-icons/Ionicons";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { Prayer } from "../domain/types";
import { colors } from "../theme";
import { formatPrayerCount } from "../utils/formatters";

export function PrayerDetail({
  prayer,
  onClose,
  onPray,
  asModal = true,
}: {
  prayer: Prayer | null;
  onClose: () => void;
  onPray: (id: string) => void;
  asModal?: boolean;
}) {
  const { bottom } = useSafeAreaInsets();
  if (!prayer) return null;
  const content = (
    <View style={styles.overlay}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="关闭祷告详情"
        style={styles.backdrop}
        onPress={onClose}
      />
      <View
        style={[styles.sheet, { paddingBottom: Math.max(30, bottom + 18) }]}
      >
        <View style={styles.handle} />
        <ScrollView
          bounces={false}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.icon}>
            <Ionicons name="earth" size={29} color={colors.white} />
          </View>
          <Text style={styles.category}>
            {prayer.flag} {prayer.location}
          </Text>
          <Text accessibilityRole="header" style={styles.title}>
            {prayer.title}
          </Text>
          <Text style={styles.body}>{prayer.excerpt}</Text>
          <Text style={styles.count}>
            {formatPrayerCount(prayer.prayerCount)} 人已一同守望
          </Text>
          <Text style={styles.prompt}>让我们安静片刻，为此献上祷告。</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: prayer.prayedByMe }}
            onPress={() => onPray(prayer.id)}
            style={({ pressed }) => [
              styles.button,
              prayer.prayedByMe && styles.buttonDone,
              pressed && styles.pressed,
            ]}
          >
            <Ionicons
              name={prayer.prayedByMe ? "checkmark-circle" : "heart"}
              size={20}
              color={colors.white}
            />
            <Text style={styles.buttonText}>
              {prayer.prayedByMe ? "已与他们一同祷告" : "阿们，我愿意祷告"}
            </Text>
          </Pressable>
          <Pressable accessibilityRole="button" hitSlop={8} onPress={onClose}>
            <Text style={styles.close}>关闭</Text>
          </Pressable>
        </ScrollView>
      </View>
    </View>
  );
  if (!asModal) return content;
  return (
    <Modal visible animationType="fade" transparent onRequestClose={onClose}>
      {content}
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(10,25,21,.48)",
    justifyContent: "flex-end",
  },
  backdrop: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0 },
  sheet: {
    maxHeight: "86%",
    backgroundColor: colors.cream,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 25,
    paddingTop: 10,
  },
  handle: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: "#AEB9B4",
    alignSelf: "center",
    marginBottom: 8,
  },
  content: { alignItems: "center", paddingTop: 10 },
  icon: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.green,
    alignItems: "center",
    justifyContent: "center",
  },
  category: { fontSize: 13, color: colors.inkSoft, marginTop: 14 },
  title: {
    fontSize: 23,
    lineHeight: 31,
    fontWeight: "700",
    color: colors.ink,
    textAlign: "center",
    marginTop: 10,
  },
  body: {
    fontSize: 15,
    lineHeight: 24,
    color: colors.inkSoft,
    textAlign: "center",
    marginTop: 12,
  },
  count: { fontSize: 12, color: colors.inkSoft, marginTop: 14 },
  prompt: { fontSize: 13, color: "#8D641F", fontWeight: "700", marginTop: 12 },
  button: {
    minHeight: 50,
    borderRadius: 25,
    backgroundColor: colors.green,
    paddingHorizontal: 24,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginTop: 20,
  },
  buttonDone: { backgroundColor: "#8D641F" },
  buttonText: { fontSize: 14, fontWeight: "700", color: colors.white },
  close: { fontSize: 14, color: colors.inkSoft, marginTop: 20, padding: 10 },
  pressed: { opacity: 0.72 },
});
