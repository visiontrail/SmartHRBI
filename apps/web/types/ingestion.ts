export type IngestionBusinessType = "roster" | "project_progress" | "attendance" | "other";
export type IngestionWriteMode = "update_existing" | "time_partitioned_new_table" | "new_table";
export type IngestionTimeGrain = "none" | "month" | "quarter" | "year";

export type IngestionSetupQuestion = {
  questionId: string;
  title: string;
  options: string[];
};

export type IngestionCatalogSetupSeed = {
  businessType: IngestionBusinessType;
  tableName: string;
  humanLabel: string;
  writeMode: IngestionWriteMode;
  timeGrain: IngestionTimeGrain;
  primaryKeys: string[];
  matchColumns: string[];
  isActiveTarget: boolean;
  description: string;
};
