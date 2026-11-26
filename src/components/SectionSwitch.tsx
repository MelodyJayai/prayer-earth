import { memo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors } from "../theme";

export type BoardSection = "prayers" | "missions";

const sections: { value: BoardSection; label: string }[] = [
  { value: "prayers", label: "需要祷告" },
  { value: "missions", label: "宣教动态·报告·会议" },
];

/** Two sibling boards under the prayer tab. The active one is not pressable. */
export const SectionSwitch = memo(function SectionSwitch({
  active,
  onSelect,
}: {
  active: BoardSection;
  onSelect: (section: BoardSection) => void;
}) {
  return (
    <View style={styles.row} accessibilityRole="tablist">
      {sections.map((item) => {
        const selected = item.value === active;
        return (
          <Pressable
            key={item.value}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            disabled={selected}
            onPress={() => onSelect(item.value)}
            style={[styles.tab, selected && styles.tabActive]}
          >
            <Text style={[styles.text, selected && styles.textActive]}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
});

const styles = StyleSheet.create({
  row: { flexDirection: "row", backgroundColor: colors.mint, borderRadius: 14, padding: 4, gap: 4, marginBottom: 16 },
  tab: { flex: 1, alignItems: "center", paddingVertical: 10, paddingHorizontal: 6, borderRadius: 11 },
  tabActive: { backgroundColor: colors.green },
  text: { color: colors.greenDark, fontSize: 13, fontWeight: "700", textAlign: "center" },
  textActive: { color: colors.white },
});
