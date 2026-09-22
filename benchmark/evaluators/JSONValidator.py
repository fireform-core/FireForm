from typing import Any, List


class JSONValidator:
    def __init__(self):
        pass

    @staticmethod
    def json_shape_validator(json1: Any, json2: Any, path: str = "root") -> List[str]:
        """
        Recursively finds all structural disparities between json1 and json2,
        returning a list of descriptive differences with exact JSON paths.
        """
        differences = []
        if type(json1) != type(json2):
            differences.append(
                f"Type mismatch at '{path}': json1 is {type(json1).__name__}, while json2 is {type(json2).__name__}"
            )
            return differences

        if isinstance(json1, dict):
            keys1 = set(json1.keys())
            keys2 = set(json2.keys())

            missing_in_1 = keys2 - keys1
            extra_in_1 = keys1 - keys2

            if missing_in_1:
                differences.append(f"Missing keys in json1 at '{path}': {sorted(list(missing_in_1))}")
            if extra_in_1:
                differences.append(f"Extra keys in json1 at '{path}': {sorted(list(extra_in_1))}")

            common_keys = keys1 & keys2
            for key in sorted(common_keys):
                sub_path = key if path == "root" else f"{path}.{key}"
                sub_diffs = JSONValidator.json_shape_validator(
                    json1[key], json2[key], path=sub_path
                )
                differences.extend(sub_diffs)

        elif isinstance(json1, list):
            # Check element schemas without enforcing identical list lengths
            if json2 and len(json2) > 0:
                archetype = json2[0]
                for i, item in enumerate(json1):
                    sub_diffs = JSONValidator.json_shape_validator(
                        item, archetype, path=f"{path}[{i}]"
                    )
                    differences.extend(sub_diffs)
            elif json1 and len(json1) > 0 and (not json2 or len(json2) == 0):
                # If json2 has no archetype to compare against, just verify all elements in json1 share the same type
                archetype = json1[0]
                for i, item in enumerate(json1[1:], start=1):
                    sub_diffs = JSONValidator.json_shape_validator(
                        item, archetype, path=f"{path}[{i}]"
                    )
                    differences.extend(sub_diffs)

        return differences

    @staticmethod
    def json_shape_validator_with_log(json1: Any, json2: Any, verbose: bool = True) -> bool:
        """
        Checks if two dictionaries/JSON structures have the same structure.
        When disparities exist and verbose=True, prints where the disparities are located.
        """
        diffs = JSONValidator.json_shape_validator(json1, json2)
        if diffs:
            if verbose:
                print(f"[JSONValidator] Found {len(diffs)} structural disparity/disparities:")
                for d in diffs:
                    print(f"  - {d}")
            return False
        return True
    