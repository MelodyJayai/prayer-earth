import { memo, type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors } from "../theme";

type Props = {
  title: string;
  subtitle: string;
  action?: ReactNode;
};

export const PageHeader = memo(function PageHeader({
  title,
  subtitle,
  action,
}: Props) {
  return (
    <View style={styles.header}>
      <View style={styles.copy}>
        <Text style={styles.eyebrow}>{subtitle}</Text>
        <Text style={styles.title}>{title}</Text>
      </View>
      {action}
    </View>
  );
});

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 22,
  },
  copy: { flex: 1, paddingRight: 12 },
  eyebrow: {
    fontSize: 13,
    color: colors.inkSoft,
    letterSpacing: 0.3,
    marginBottom: 5,
  },
  title: {
    fontSize: 28,
    fontWeight: "700",
    color: colors.ink,
    letterSpacing: -0.7,
  },
});
