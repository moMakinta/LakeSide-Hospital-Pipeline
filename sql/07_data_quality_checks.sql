/* 07 - Checks to run after a load. Everything should say PASS. */
USE LakesideHospital;
GO

WITH Checks AS (
    SELECT 'Landed admissions missing from core' AS CheckName, COUNT(*) AS FailedRows
    FROM   landing.Admission AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.FactAdmission AS f WHERE f.AdmissionID = s.AdmissionID)
    UNION ALL
    SELECT 'Landed charges missing from core', COUNT(*)
    FROM   landing.Charge AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.FactCharge AS f WHERE f.SourceChargeID = s.ChargeID)
    UNION ALL
    SELECT 'Landed payments missing from core', COUNT(*)
    FROM   landing.Payment AS s
    WHERE  NOT EXISTS (SELECT 1 FROM core.FactPayment AS f WHERE f.PaymentID = s.PaymentID)
    UNION ALL
    SELECT 'Captured charges loaded more than once', COUNT(*)
    FROM  (SELECT SourceChargeID FROM core.FactCharge WHERE ChargeSource = 'Captured'
           GROUP BY SourceChargeID HAVING COUNT(*) > 1) AS x
    UNION ALL
    SELECT 'Charge lines where funder + patient <> amount', COUNT(*)
    FROM   core.FactCharge
    WHERE  FunderAmount + PatientAmount <> Amount
    UNION ALL
    SELECT 'Charge lines with a negative or zero amount', COUNT(*)
    FROM   core.FactCharge
    WHERE  Amount <= 0 OR FunderAmount < 0 OR PatientAmount < 0
    UNION ALL
    SELECT 'Private accounts with something charged to a funder', COUNT(*)
    FROM   core.FactCharge    AS c
    JOIN   core.FactAdmission AS a  ON a.AdmissionKey = c.AdmissionKey
    JOIN   core.DimFunder     AS fu ON fu.FunderKey   = a.FunderKey
    WHERE  fu.CoverPct = 0 AND c.FunderAmount <> 0
    UNION ALL
    -- for a discharged patient the number of accommodation lines must equal the length of stay
    SELECT 'Discharged admissions where nights charged <> length of stay', COUNT(*)
    FROM  (SELECT a.AdmissionKey
           FROM   core.FactAdmission AS a
           LEFT JOIN core.FactCharge AS c ON c.AdmissionKey = a.AdmissionKey AND c.ChargeSource = 'Accommodation'
           WHERE  a.DischargeDateTime IS NOT NULL
           GROUP BY a.AdmissionKey, a.LengthOfStayDays
           HAVING COUNT(c.ChargeKey) <> a.LengthOfStayDays) AS x
    UNION ALL
    SELECT 'Ward nights with more patients than beds', COUNT(*)
    FROM  (SELECT a.WardKey, c.ServiceDateKey
           FROM   core.FactCharge    AS c
           JOIN   core.FactAdmission AS a ON a.AdmissionKey = c.AdmissionKey
           JOIN   core.DimWard       AS w ON w.WardKey      = a.WardKey
           WHERE  c.ChargeSource = 'Accommodation'
           GROUP BY a.WardKey, c.ServiceDateKey, w.BedCount
           HAVING COUNT(*) > w.BedCount) AS x
    UNION ALL
    SELECT 'Tariff rows with overlapping dates', COUNT(*)
    FROM   core.DimTariff AS t1
    JOIN   core.DimTariff AS t2 ON t2.TariffCode = t1.TariffCode
                               AND t2.TariffKey  > t1.TariffKey
                               AND t1.EffectiveFrom <= t2.EffectiveTo
                               AND t2.EffectiveFrom <= t1.EffectiveTo
    UNION ALL
    SELECT 'Admissions with discharge before admission', COUNT(*)
    FROM   core.FactAdmission
    WHERE  DischargeDateTime < AdmitDateTime
)
SELECT CheckName,
       FailedRows,
       CASE WHEN FailedRows = 0 THEN 'PASS' ELSE 'FAIL' END AS Result
FROM   Checks;
GO

-- totals to compare with the numbers in the README
SELECT (SELECT COUNT(*) FROM core.FactAdmission)                                      AS Admissions,
       (SELECT COUNT(*) FROM core.FactCharge WHERE ChargeSource = 'Captured')         AS CapturedLines,
       (SELECT COUNT(*) FROM core.FactCharge WHERE ChargeSource = 'Accommodation')    AS AccommodationLines,
       (SELECT SUM(Amount) FROM core.FactCharge)                                      AS TotalCharged,
       (SELECT SUM(FunderAmount) FROM core.FactCharge)                                AS FunderLiable,
       (SELECT SUM(PatientAmount) FROM core.FactCharge)                               AS PatientLiable,
       (SELECT SUM(Amount) FROM core.FactPayment)                                     AS TotalPaid;

SELECT TOP (20) * FROM audit.LoadLog ORDER BY LoadLogID DESC;
GO
