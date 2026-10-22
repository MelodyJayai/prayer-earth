import { createContext, type ReactNode, useContext } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { StorageNotice } from "../components/StorageNotice";
import { usePrayerStore } from "../hooks/usePrayerStore";

type PrayerStore = ReturnType<typeof usePrayerStore>;
const PrayerContext = createContext<PrayerStore | null>(null);

export function PrayerProvider({ children }: { children: ReactNode }) {
  const store = usePrayerStore();
  return (
    <PrayerContext.Provider value={store}>
      <View style={styles.container}>
        {store.hydrated ? (
          children
        ) : (
          <View accessibilityLabel="正在恢复祷告记录" style={styles.loading}>
            <ActivityIndicator color="#1F5C4F" size="large" />
            <Text style={styles.loadingText}>正在准备祷告空间…</Text>
          </View>
        )}
        <StorageNotice
          message={store.storageWarning}
          onClose={store.clearStorageWarning}
        />
      </View>
    </PrayerContext.Provider>
  );
}

export function usePrayers(): PrayerStore {
  const value = useContext(PrayerContext);
  if (!value) throw new Error("usePrayers must be used within PrayerProvider");
  return value;
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F7F5F0",
  },
  loadingText: { marginTop: 14, color: "#526963", fontSize: 14 },
});
