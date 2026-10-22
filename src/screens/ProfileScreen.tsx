import Ionicons from "@expo/vector-icons/Ionicons";
import { memo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { PageHeader } from "../components/PageHeader";
import type { IconName } from "../domain/types";
import { colors } from "../theme";

const settings: {
  icon: IconName;
  label: string;
  value: string;
  action: "privacy" | "community" | "about";
}[] = [
  {
    icon: "shield-checkmark-outline",
    label: "隐私与数据说明",
    value: "",
    action: "privacy",
  },
  {
    icon: "people-outline",
    label: "祷告社区守则",
    value: "",
    action: "community",
  },
  {
    icon: "information-circle-outline",
    label: "关于祷告地球",
    value: "1.1.0",
    action: "about",
  },
];

export const ProfileScreen = memo(function ProfileScreen({
  prayerCount,
  onPrivacy,
  onCommunity,
  onAbout,
  onAdmin,
}: {
  prayerCount: number;
  onPrivacy: () => void;
  onCommunity: () => void;
  onAbout: () => void;
  onAdmin?: () => void;
}) {
  const actions = {
    privacy: onPrivacy,
    community: onCommunity,
    about: onAbout,
  };
  return (
    <ScrollView
      showsVerticalScrollIndicator={false}
      contentContainerStyle={styles.content}
    >
      <PageHeader title="我的旅程" subtitle="在祷告中彼此同行" />
      <View style={styles.profileCard}>
        <View style={styles.avatar}>
          <Ionicons name="person" size={32} color={colors.green} />
        </View>
        <Text style={styles.name}>平安的同行者</Text>
        <Text style={styles.subtitle}>愿你的每一次祷告，都成为爱的回声</Text>
        <View style={styles.stats}>
          <Stat value={String(prayerCount)} label="祷告" />
          <Stat value="18" label="守望天数" />
          <Stat value="7" label="关注地区" />
        </View>
      </View>
      <Text style={styles.groupTitle}>设置</Text>
      <View style={styles.settingsGroup}>
        {settings.map((row, index) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`${row.label}${row.value ? `，${row.value}` : ""}`}
            key={row.label}
            onPress={actions[row.action]}
            style={({ pressed }) => [
              styles.settingRow,
              index < settings.length - 1 && styles.settingDivider,
              pressed && styles.pressed,
            ]}
          >
            <View style={styles.settingIcon}>
              <Ionicons name={row.icon} size={20} color={colors.green} />
            </View>
            <Text style={styles.settingLabel}>{row.label}</Text>
            <Text style={styles.settingValue}>{row.value}</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
        ))}
      </View>
      {onAdmin && <>
        <Text style={styles.groupTitle}>同工内容管理</Text>
        <View style={styles.settingsGroup}>
          <Pressable accessibilityRole="button" accessibilityLabel="管理员入口，更新每日晨修与宣教动态" onPress={onAdmin} style={({ pressed }) => [styles.settingRow, pressed && styles.pressed]}>
            <View style={styles.settingIcon}><Ionicons name="create-outline" size={20} color={colors.green} /></View>
            <Text style={styles.settingLabel}>管理员入口</Text>
            <Text style={styles.settingValue}>需授权登录</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
        </View>
      </>}
    </ScrollView>
  );
});

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View
      style={styles.stat}
      accessible
      accessibilityLabel={`${label} ${value}`}
    >
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 120 },
  profileCard: {
    backgroundColor: colors.white,
    borderRadius: 22,
    padding: 24,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.line,
  },
  avatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.mint,
    alignItems: "center",
    justifyContent: "center",
  },
  name: { fontSize: 20, fontWeight: "700", color: colors.ink, marginTop: 12 },
  subtitle: {
    fontSize: 13,
    color: colors.inkSoft,
    marginTop: 6,
    textAlign: "center",
  },
  stats: {
    flexDirection: "row",
    marginTop: 24,
    borderTopWidth: 1,
    borderColor: colors.line,
    paddingTop: 18,
    width: "100%",
  },
  stat: { flex: 1, alignItems: "center" },
  statValue: { fontSize: 19, fontWeight: "800", color: colors.green },
  statLabel: { fontSize: 12, color: colors.inkSoft, marginTop: 3 },
  groupTitle: {
    fontSize: 13,
    fontWeight: "700",
    color: colors.inkSoft,
    marginTop: 26,
    marginBottom: 8,
  },
  settingsGroup: {
    borderRadius: 17,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.line,
  },
  settingRow: {
    minHeight: 62,
    backgroundColor: colors.white,
    paddingHorizontal: 14,
    flexDirection: "row",
    alignItems: "center",
  },
  settingDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.line,
  },
  settingIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: colors.mint,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 11,
  },
  settingLabel: { fontSize: 14, color: colors.ink, flex: 1 },
  settingValue: { fontSize: 12, color: colors.inkSoft, marginRight: 5 },
  pressed: { opacity: 0.66 },
});
