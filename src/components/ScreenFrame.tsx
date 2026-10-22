import type { ReactNode } from "react";
import { StyleSheet, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "../theme";

export function ScreenFrame({
  children,
}: {
  children: (wide: boolean) => ReactNode;
}) {
  const { width } = useWindowDimensions();
  const wide = width >= 760;
  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <View style={[styles.shell, wide && styles.wide]}>{children(wide)}</View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.cream },
  shell: { flex: 1, backgroundColor: colors.cream },
  wide: {
    width: "100%",
    maxWidth: 860,
    alignSelf: "center",
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderColor: colors.line,
  },
});
