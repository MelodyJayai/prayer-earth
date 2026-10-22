import Ionicons from "@expo/vector-icons/Ionicons";
import { memo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { AppTab, IconName } from "../domain/types";
import { colors } from "../theme";

const tabs: { label: AppTab; icon: IconName; filled: IconName }[] = [
  { label: "首页", icon: "home-outline", filled: "home" },
  { label: "祷告", icon: "earth-outline", filled: "earth" },
  { label: "见证", icon: "book-outline", filled: "book" },
  { label: "我的", icon: "person-outline", filled: "person" },
];

export const BottomNav = memo(function BottomNav({
  tab,
  onTab,
  onCompose,
}: {
  tab: AppTab;
  onTab: (tab: AppTab) => void;
  onCompose: () => void;
}) {
  const { bottom } = useSafeAreaInsets();
  return (
    <View style={[styles.nav, { height: 68 + bottom, paddingBottom: bottom }]}>
      <View style={styles.items}>
        {tabs.slice(0, 2).map((item) => (
          <NavItem
            key={item.label}
            {...item}
            active={tab === item.label}
            onPress={onTab}
          />
        ))}
        <View style={styles.gap} />
        {tabs.slice(2).map((item) => (
          <NavItem
            key={item.label}
            {...item}
            active={tab === item.label}
            onPress={onTab}
          />
        ))}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="发布新的祷告"
        hitSlop={8}
        onPress={onCompose}
        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
      >
        <Ionicons name="add" size={31} color={colors.white} />
      </Pressable>
    </View>
  );
});

const NavItem = memo(function NavItem({
  label,
  icon,
  filled,
  active,
  onPress,
}: {
  label: AppTab;
  icon: IconName;
  filled: IconName;
  active: boolean;
  onPress: (tab: AppTab) => void;
}) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityLabel={label}
      accessibilityState={{ selected: active }}
      onPress={() => onPress(label)}
      style={({ pressed }) => [styles.item, pressed && styles.pressed]}
    >
      <Ionicons
        name={active ? filled : icon}
        size={23}
        color={active ? colors.green : colors.muted}
      />
      <Text style={[styles.label, active && styles.activeLabel]}>{label === "见证" ? "晨修·宣教" : label}</Text>
    </Pressable>
  );
});

const styles = StyleSheet.create({
  nav: {
    position: "relative",
    backgroundColor: "rgba(255,255,255,.98)",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: colors.line,
  },
  items: { flexDirection: "row", height: 68, alignItems: "center" },
  item: {
    flex: 1,
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },
  gap: { width: 68 },
  label: { fontSize: 11, color: colors.muted },
  activeLabel: { color: colors.green, fontWeight: "700" },
  fab: {
    position: "absolute",
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: colors.green,
    alignItems: "center",
    justifyContent: "center",
    top: -23,
    left: "50%",
    marginLeft: -29,
    borderWidth: 5,
    borderColor: colors.cream,
    shadowColor: colors.greenDark,
    shadowOpacity: 0.22,
    shadowRadius: 9,
    shadowOffset: { width: 0, height: 4 },
    elevation: 7,
  },
  pressed: { opacity: 0.65, transform: [{ scale: 0.96 }] },
});
