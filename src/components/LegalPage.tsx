import Ionicons from "@expo/vector-icons/Ionicons";
import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "../theme";

export type LegalSection = { heading: string; body: string };

export function LegalPage({
  eyebrow,
  title,
  intro,
  sections,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  sections: LegalSection[];
}) {
  const router = useRouter();
  return (
    <SafeAreaView
      style={styles.safe}
      edges={["top", "bottom", "left", "right"]}
    >
      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="返回"
          hitSlop={8}
          onPress={() => router.back()}
          style={styles.back}
        >
          <Ionicons name="chevron-back" size={24} color={colors.ink} />
        </Pressable>
        <Text style={styles.headerTitle}>{title}</Text>
        <View style={styles.headerSpacer} />
      </View>
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.eyebrow}>{eyebrow}</Text>
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        <Text style={styles.intro}>{intro}</Text>
        {sections.map((section) => (
          <View key={section.heading} style={styles.section}>
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              {section.heading}
            </Text>
            <Text style={styles.body}>{section.body}</Text>
          </View>
        ))}
        <Text style={styles.updated}>最后更新：2026年8月24日</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.cream },
  header: {
    height: 56,
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.line,
    paddingHorizontal: 12,
  },
  back: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    flex: 1,
    textAlign: "center",
    fontSize: 16,
    fontWeight: "700",
    color: colors.ink,
  },
  headerSpacer: { width: 44 },
  content: {
    width: "100%",
    maxWidth: 760,
    alignSelf: "center",
    padding: 24,
    paddingBottom: 60,
  },
  eyebrow: {
    color: colors.green,
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 1,
  },
  title: {
    color: colors.ink,
    fontSize: 30,
    lineHeight: 38,
    fontWeight: "700",
    marginTop: 8,
  },
  intro: { color: colors.inkSoft, fontSize: 15, lineHeight: 24, marginTop: 12 },
  section: { marginTop: 28 },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 8,
  },
  body: { color: colors.inkSoft, fontSize: 14, lineHeight: 24 },
  updated: { color: colors.inkSoft, fontSize: 12, marginTop: 36 },
});
