import Ionicons from "@expo/vector-icons/Ionicons";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors } from "../theme";

export function StorageNotice({
  message,
  onClose,
}: {
  message: string | null;
  onClose: () => void;
}) {
  const { top } = useSafeAreaInsets();
  if (!message) return null;
  return (
    <View
      accessibilityLiveRegion="polite"
      style={[styles.notice, { top: Math.max(12, top + 8) }]}
    >
      <Ionicons
        name="information-circle-outline"
        size={20}
        color={colors.ink}
      />
      <Text style={styles.text}>{message}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="关闭提示"
        hitSlop={8}
        onPress={onClose}
      >
        <Ionicons name="close" size={20} color={colors.ink} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  notice: {
    position: "absolute",
    left: 16,
    right: 16,
    zIndex: 20,
    minHeight: 50,
    borderRadius: 14,
    paddingHorizontal: 14,
    backgroundColor: "#FFF5D9",
    borderWidth: 1,
    borderColor: "#D8B66C",
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
  },
  text: { flex: 1, color: colors.ink, fontSize: 13, lineHeight: 19 },
});
