export interface Bank {models:{id:string;display_name:string;family:string;family_name?:string;counts:number[]}[];calibration:Record<string,{beta:number;cv_accuracy:number}>;robust:unknown}
export interface ProbeOutput {text:string;expected_count:number}
export interface TraceResult {prediction:string;prediction_name:string;probability:number;used_outputs:number;results:{model:string;display_name:string;probability:number;profile_similarity:number;family:string;family_name:string}[];diagnostics:{index:number;parsed_numbers:number;minimum_numbers:number;accepted:boolean}[];family_prediction_name:string;family_probability:number;method:string}
export function parseNumbers(text:string):number[]
export function analyzeGlobalOutputs(outputs:ProbeOutput[],bank:Bank):TraceResult
