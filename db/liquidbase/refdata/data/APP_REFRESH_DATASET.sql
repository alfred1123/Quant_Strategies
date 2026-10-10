-- The Refresh dataset checkbox follows this flag. Yahoo may refetch.
-- Glassnode is filled by its own schedule. Bybit reads captured bars.
-- Neither is called from this checkbox.
UPDATE REFDATA.APP
   SET REFRESH_DATASET_IND = 'N', UPDATED_AT = now()
 WHERE NAME IN ('glassnode', 'bybit');

UPDATE REFDATA.APP
   SET REFRESH_DATASET_IND = 'Y', UPDATED_AT = now()
 WHERE REFRESH_DATASET_IND IS NULL;
